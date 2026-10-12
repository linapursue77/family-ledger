# -*- coding: utf-8 -*-
"""短信网关：可插拔，未配置密钥时降级为「打日志」模式。

为什么这么设计：
    国内短信服务要求「企业营业执照 + 短信签名/模板报备」，个人主体办不了。
    但功能不能因此残缺——所以做成两种驱动：

    console（默认，零成本）
        验证码只写日志，不真发短信。个人主体 / 本地联调时，整条找回密码流程
        照样能完整走通，从日志里抄验证码即可。
    aliyun / tencent
        配上密钥就自动切到真发短信，业务代码一行都不用改。

    想接别的服务商，实现 send_code() 后注册进 _DRIVERS 即可。
"""
import hashlib
import logging
import random
import time

import httpx
from django.conf import settings
from django.utils.crypto import get_random_string

logger = logging.getLogger(__name__)


class SmsError(Exception):
    """短信发送失败。"""


def generate_code(length: int = None) -> str:
    """生成数字验证码。用 crypto 模块而非 random，保证不可预测。"""
    n = length or getattr(settings, 'SMS_CODE_LENGTH', 6)
    return ''.join(random.SystemRandom().choice('0123456789') for _ in range(n))


def mask_phone(phone: str) -> str:
    """脱敏：138****8000。日志里绝不打完整手机号。"""
    if not phone or len(phone) < 7:
        return phone or ''
    return f'{phone[:3]}****{phone[-4:]}'


def _console_driver(phone: str, code: str, scene: str) -> None:
    """开发/未配置：验证码写日志。"""
    logger.info(
        '[短信·控制台模式] 手机号=%s 场景=%s 验证码=%s（%d 分钟内有效）'
        '—— 生产环境请配置 SMS_ACCESS_KEY 等密钥，否则用户收不到短信',
        mask_phone(phone), scene, code,
        getattr(settings, 'SMS_CODE_TTL', 300) // 60,
    )


def _aliyun_driver(phone: str, code: str, scene: str) -> None:
    """阿里云短信服务。需要：签名 + 模板 + AccessKey。"""
    ak = settings.SMS_ACCESS_KEY
    sk = settings.SMS_ACCESS_SECRET
    sign_name = settings.SMS_SIGN_NAME
    template_code = _template_for(scene)
    if not all([ak, sk, sign_name, template_code]):
        raise SmsError('阿里云短信配置不完整（需 SMS_ACCESS_KEY / SECRET / SIGN_NAME / 模板）')

    # 阿里云新版 SDK 走 RPC + 签名 v1.0，这里直接用 HTTP 签名，避免引入重型 SDK
    import hmac
    import base64
    from urllib.parse import urlencode

    params = {
        'AccessKeyId': ak,
        'Action': 'SendSms',
        'Format': 'JSON',
        'PhoneNumbers': phone,
        'RegionId': 'cn-hangzhou',
        'SignName': sign_name,
        'SignatureMethod': 'HMAC-SHA1',
        'SignatureNonce': get_random_string(32),
        'SignatureVersion': '1.0',
        'TemplateCode': template_code,
        'TemplateParam': f'{{"code":"{code}"}}',
        'Timestamp': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'Version': '2017-05-25',
    }
    # 规范化的待签串
    sorted_params = sorted(params.items())
    canonical = urlencode(sorted_params, quote_via=lambda s, *_a, **_k: _percent_encode(s))
    string_to_sign = 'GET&%2F&' + _percent_encode(canonical)
    key = (sk + '&').encode()
    signature = base64.b64encode(
        hmac.new(key, string_to_sign.encode(), hashlib.sha1).digest()
    ).decode()
    params['Signature'] = signature

    try:
        resp = httpx.get('https://dysmsapi.aliyuncs.com/', params=params, timeout=10)
        result = resp.json()
    except Exception as exc:
        raise SmsError(f'短信服务请求失败：{exc}') from exc

    if result.get('Code') != 'OK':
        raise SmsError(result.get('Message') or '短信发送失败')


def _percent_encode(s: str) -> str:
    """阿里云要求的百分号编码：+→%20、*→%2A、~→%7E。"""
    from urllib.parse import quote
    return quote(str(s), safe='').replace('+', '%20').replace('*', '%2A').replace('%7E', '~')


def _tencent_driver(phone: str, code: str, scene: str) -> None:
    """腾讯云短信。需要：SDKAppID + 签名 + 模板 + SecretId/Key（TC3 签名）。"""
    import hmac
    import json

    secret_id = settings.SMS_ACCESS_KEY
    secret_key = settings.SMS_ACCESS_SECRET
    app_id = settings.SMS_APP_ID
    sign_name = settings.SMS_SIGN_NAME
    template_id = _template_for(scene)
    if not all([secret_id, secret_key, app_id, sign_name, template_id]):
        raise SmsError('腾讯云短信配置不完整（需 SMS_APP_ID / ACCESS_KEY / SECRET / SIGN_NAME / 模板）')

    host, service, action, version = 'sms.tencentcloudapi.com', 'sms', 'SendSms', '2021-01-11'
    payload = {
        'PhoneNumberSet': [f'+86{phone}'],
        'SmsSdkAppId': app_id,
        'SignName': sign_name,
        'TemplateId': template_id,
        'TemplateParamSet': [code],
    }
    body = json.dumps(payload, separators=(',', ':'), ensure_ascii=False)
    timestamp = int(time.time())
    date = time.strftime('%Y-%m-%d', time.gmtime(timestamp))

    def _sign(key, msg):
        return hmac.new(key, msg.encode('utf-8'), hashlib.sha256).digest()

    canonical_request = '\n'.join([
        'POST', '/', '', f'content-type:application/json\nhost:{host}\n',
        'content-type;host',
        hashlib.sha256(body.encode('utf-8')).hexdigest(),
    ])
    credential_scope = f'{date}/{service}/tc3_request'
    string_to_sign = '\n'.join([
        'TC3-HMAC-SHA256', str(timestamp), credential_scope,
        hashlib.sha256(canonical_request.encode('utf-8')).hexdigest(),
    ])
    secret_date = _sign(('TC3' + secret_key).encode('utf-8'), date)
    secret_service = _sign(secret_date, service)
    secret_signing = _sign(secret_service, 'tc3_request')
    signature = hmac.new(secret_signing, string_to_sign.encode('utf-8'),
                         hashlib.sha256).hexdigest()
    authorization = (
        f'TC3-HMAC-SHA256 Credential={secret_id}/{credential_scope}, '
        f'SignedHeaders=content-type;host, Signature={signature}'
    )

    try:
        resp = httpx.post(
            f'https://{host}/',
            content=body.encode('utf-8'),
            headers={
                'Authorization': authorization,
                'Content-Type': 'application/json',
                'Host': host,
                'X-TC-Action': action,
                'X-TC-Version': version,
                'X-TC-Timestamp': str(timestamp),
            },
            timeout=10,
        )
        result = resp.json()
    except Exception as exc:
        raise SmsError(f'短信服务请求失败：{exc}') from exc

    err = (result.get('Response') or {}).get('Error')
    if err:
        raise SmsError(err.get('Message') or '短信发送失败')


_DRIVERS = {
    'console': _console_driver,
    'aliyun': _aliyun_driver,
    'tencent': _tencent_driver,
}


def _template_for(scene: str) -> str:
    """按场景取模板 ID / Code。"""
    mapping = {
        'reset_password': settings.SMS_TEMPLATE_RESET,
        'bind_phone': settings.SMS_TEMPLATE_BIND,
    }
    return mapping.get(scene, settings.SMS_TEMPLATE_RESET)


def send_code(phone: str, code: str, scene: str = 'reset_password') -> None:
    """发验证码。按 SMS_PROVIDER 选驱动，未配置任何密钥时自动退回 console。

    调用方不需要关心当前是哪种模式——这保证「没有短信服务」时功能依然可测、可用。
    """
    provider = (getattr(settings, 'SMS_PROVIDER', '') or '').lower()
    if provider == 'aliyun' and settings.SMS_ACCESS_KEY:
        driver = _aliyun_driver
    elif provider == 'tencent' and settings.SMS_ACCESS_KEY:
        driver = _tencent_driver
    else:
        driver = _console_driver
    driver(phone, code, scene)
