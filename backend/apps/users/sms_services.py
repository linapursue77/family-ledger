# -*- coding: utf-8 -*-
"""短信验证码业务：发送 / 校验 / 限流。

安全设计（这几点是验证码功能的成败所在）：
1. 防用户枚举：手机号没注册时，对外一样返回「已发送」，只是内部不真发。
   否则攻击者拿接口一撞就能知道谁注册过这个 App。
2. 防轰炸：同一手机号 60 秒一条、每天 N 条；同一 IP 每天上限，防止刷别人手机。
3. 防暴力破解：验证码 6 位只有 100 万种，必须限制校验次数，错满即作废。
4. 一次性：用掉立刻标记，防重放。
5. 只存哈希：DB 泄漏也拿不到可用验证码。
"""
import logging

from django.contrib.auth.hashers import check_password, make_password
from django.core.cache import cache
from django.utils import timezone
from datetime import timedelta

from apps.users import sms as sms_gateway
from apps.users.models import SmsCode

logger = logging.getLogger(__name__)

SCENE_LABELS = {
    SmsCode.SCENE_RESET: '重置密码',
    SmsCode.SCENE_BIND: '绑定手机号',
}


class SmsThrottled(Exception):
    """发送过于频繁。"""


def _ttl() -> int:
    from django.conf import settings
    return getattr(settings, 'SMS_CODE_TTL', 300)


def _interval() -> int:
    from django.conf import settings
    return getattr(settings, 'SMS_SEND_INTERVAL', 60)


def _max_tries() -> int:
    from django.conf import settings
    return getattr(settings, 'SMS_MAX_TRIES', 5)


def _check_throttle(phone: str, ip: str, scene: str) -> None:
    """发送频率限制。用 cache 即可——限流丢了最多是多发一条，不致命。"""
    from django.conf import settings

    if cache.get(f'sms:interval:{scene}:{phone}'):
        raise SmsThrottled(f'发送太频繁了，请 {_interval()} 秒后再试')

    daily_key = f'sms:daily:{phone}'
    daily = cache.get(daily_key) or 0
    limit = getattr(settings, 'SMS_DAILY_LIMIT_PER_PHONE', 10)
    if daily >= limit:
        raise SmsThrottled('今天发送次数已达上限，请明天再试')

    if ip:
        ip_key = f'sms:daily:ip:{ip}'
        ip_count = cache.get(ip_key) or 0
        ip_limit = getattr(settings, 'SMS_DAILY_LIMIT_PER_IP', 30)
        if ip_count >= ip_limit:
            raise SmsThrottled('操作过于频繁，请稍后再试')
        cache.set(ip_key, ip_count + 1, timeout=86400)


def _mark_sent(phone: str, scene: str) -> None:
    cache.set(f'sms:interval:{scene}:{phone}', 1, timeout=_interval())
    daily_key = f'sms:daily:{phone}'
    cache.set(daily_key, (cache.get(daily_key) or 0) + 1, timeout=86400)


def send_code(phone: str, scene: str = SmsCode.SCENE_RESET, ip: str = '',
              must_registered: bool = True) -> dict:
    """发送验证码。

    must_registered=True 时（重置密码场景），手机号不存在也要返回成功——
    不能让调用方区分「发了」和「这号没注册」，否则就是用户枚举漏洞。
    返回 sent 字段仅用于内部与开发提示，对外请统一文案。
    """
    from apps.users.models import User

    _check_throttle(phone, ip, scene)

    exists = User.objects.filter(phone=phone).exists()
    if must_registered and not exists:
        # 防枚举：对外报「已发送」，实际不消耗短信额度，也不落库
        logger.info('验证码请求：手机号未注册，静默跳过 scene=%s phone=%s',
                    scene, sms_gateway.mask_phone(phone))
        return {'sent': False, 'exists': False}

    code = sms_gateway.generate_code()
    SmsCode.objects.create(
        phone=phone,
        scene=scene,
        code_hash=make_password(code),
        expires_at=timezone.now() + timedelta(seconds=_ttl()),
        ip=ip or '',
    )
    try:
        sms_gateway.send_code(phone, code, scene)
    except Exception as exc:
        logger.error('短信发送失败 phone=%s scene=%s: %s',
                     sms_gateway.mask_phone(phone), scene, exc)
        # 网关挂了不要把错误暴露给用户（可能含密钥信息），但 DEVELOP 模式要能看见
        from django.conf import settings
        if settings.DEBUG:
            raise
        return {'sent': False, 'exists': True, 'error': '短信服务暂不可用，请稍后再试'}

    _mark_sent(phone, scene)
    return {'sent': True, 'exists': True}


def verify_code(phone: str, scene: str, code: str, consume: bool = True):
    """校验验证码。返回 SmsCode 或抛 ValueError（带可直接展示的中文文案）。"""
    record = (SmsCode.objects
              .filter(phone=phone, scene=scene, used_at__isnull=True)
              .order_by('-created_at')
              .first())
    if record is None:
        raise ValueError('验证码已失效，请重新获取')

    if record.is_expired():
        raise ValueError('验证码已过期，请重新获取')

    if record.try_count >= _max_tries():
        # 错太多次，把这条作废，逼用户重新获取，避免无限试
        record.used_at = timezone.now()
        record.save(update_fields=['used_at'])
        raise ValueError('验证码错误次数过多，请重新获取')

    if not check_password(code or '', record.code_hash):
        record.try_count += 1
        left = _max_tries() - record.try_count
        fields = ['try_count']
        if left <= 0:
            # 次数用尽就当场作废，别留着等下一次请求才失效——
            # 否则这条验证码在「已用尽但未标记」的窗口里仍是可用状态
            record.used_at = timezone.now()
            fields.append('used_at')
        record.save(update_fields=fields)
        raise ValueError(f'验证码不正确，还可尝试 {left} 次' if left > 0
                         else '验证码错误次数过多，请重新获取')

    if consume:
        record.used_at = timezone.now()
        record.save(update_fields=['used_at'])
    return record


def cleanup_expired(days: int = 7) -> int:
    """清掉过期记录，避免表无限膨胀（可挂定时任务或 manage.py 清理）。"""
    cutoff = timezone.now() - timedelta(days=days)
    deleted, _ = SmsCode.objects.filter(created_at__lt=cutoff).delete()
    return deleted
