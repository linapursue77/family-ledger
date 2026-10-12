# -*- coding: utf-8 -*-
"""微信支付 v3 客户端：JSAPI / H5 下单、查单、回调验签解密。

只封装「跟微信打交道」的部分，订单落库、开通会员都在 services/views 里，
换支付渠道时只需替换本文件。

对接前置条件（商户平台 + 公众号/小程序后台）：
1. 商户号 mchid、API v3 密钥、API 证书（拿到证书序列号 serial_no 与私钥 pem）；
2. 公众号（或小程序）appid + secret，并且已绑定微信支付商户号；
3. 配置支付回调域名 / 网页授权域名。

依赖：pip install cryptography
"""
import base64
import json
import logging
import secrets
import time
from pathlib import Path

import httpx
from django.conf import settings

from apps.core.response import BusinessError

logger = logging.getLogger('django.request')

WXPAY_HOST = 'https://api.mch.weixin.qq.com'
# JSAPI / H5 各自的 trade_type 与下单路径
TRADE_JSAPI = 'JSAPI'
TRADE_H5 = 'MWEB'
PATH_JSAPI = '/v3/pay/transactions/jsapi'
PATH_H5 = '/v3/pay/transactions/h5'
# 支付成功的 trade_state
TRADE_STATE_SUCCESS = 'SUCCESS'
# 终态且失败的状态：查单发现后就关掉本地订单
TRADE_STATE_FAILED = {'CLOSED', 'REVOKED', 'PAYERROR'}

# 平台证书缓存：{serial_no: x509 证书对象}
_platform_certs: dict = {}


class WeChatPayError(BusinessError):
    """微信支付调用失败：消息可直接回给前端。"""


def _crypto():
    """延迟导入 cryptography，没装依赖时不至于让整个项目起不来。"""
    try:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        from cryptography import x509
    except ImportError as exc:  # pragma: no cover - 依赖缺失
        raise WeChatPayError('缺少依赖 cryptography，请先 pip install cryptography') from exc
    return hashes, serialization, padding, AESGCM, x509


def _private_key():
    """商户 API 私钥：优先读环境变量里的 PEM，其次读证书文件。"""
    _, serialization, _, _, _ = _crypto()
    pem = settings.WXPAY_PRIVATE_KEY
    if pem:
        pem = pem.replace('\\n', '\n')
    else:
        path = Path(settings.WXPAY_PRIVATE_KEY_PATH)
        if not path.exists():
            raise WeChatPayError('未配置商户 API 私钥（WXPAY_PRIVATE_KEY / _PATH）')
        pem = path.read_text(encoding='utf-8')
    try:
        return serialization.load_pem_private_key(pem.encode('utf-8'), password=None)
    except Exception as exc:
        raise WeChatPayError(f'商户私钥解析失败：{exc}') from exc


def _rsa_sign(message: str) -> str:
    _, _, padding, _, _ = _crypto()
    from cryptography.hazmat.primitives import hashes

    signature = _private_key().sign(message.encode('utf-8'), padding.PKCS1v15(),
                                    hashes.SHA256())
    return base64.b64encode(signature).decode()


def _nonce() -> str:
    return secrets.token_hex(16)


def _authorization(method: str, path: str, body: str = '') -> str:
    """构造 WECHATPAY2-SHA256-RSA2048 请求签名头。"""
    timestamp = str(int(time.time()))
    nonce = _nonce()
    message = f'{method}\n{path}\n{timestamp}\n{nonce}\n{body}\n'
    sign = _rsa_sign(message)
    return (f'WECHATPAY2-SHA256-RSA2048 '
            f'mchid="{settings.WXPAY_MCHID}",'
            f'nonce_str="{nonce}",'
            f'signature="{sign}",'
            f'timestamp="{timestamp}",'
            f'serial_no="{settings.WXPAY_SERIAL_NO}"')


def _check_config():
    missing = [name for name, value in (
        ('WXPAY_MCHID', settings.WXPAY_MCHID),
        ('WXPAY_API_V3_KEY', settings.WXPAY_API_V3_KEY),
        ('WXPAY_SERIAL_NO', settings.WXPAY_SERIAL_NO),
        ('WXPAY_NOTIFY_URL', settings.WXPAY_NOTIFY_URL),
    ) if not value]
    if missing:
        raise WeChatPayError('微信支付未配置完整：' + '、'.join(missing))


def _request(method: str, path: str, body: dict | None = None) -> dict:
    """发一个 API v3 请求，失败直接抛 WeChatPayError（带微信返回的中文原因）。"""
    _check_config()
    payload = json.dumps(body, ensure_ascii=False, separators=(',', ':')) if body else ''
    headers = {
        'Authorization': _authorization(method, path, payload),
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'User-Agent': 'family-ledger/1.0',
    }
    try:
        resp = httpx.request(method, WXPAY_HOST + path,
                             content=payload.encode('utf-8') if payload else b'',
                             headers=headers, timeout=settings.WXPAY_TIMEOUT)
    except httpx.HTTPError as exc:
        raise WeChatPayError(f'微信支付请求失败：{exc}') from exc

    if resp.status_code >= 400:
        try:
            detail = resp.json()
        except ValueError:
            detail = {}
        raise WeChatPayError(f'{detail.get("message") or detail.get("code") or resp.text}')
    if not resp.content:
        return {}
    return resp.json()


def _appid(trade_type: str, scene: str = '') -> str:
    """小程序用小程序 appid，其它用公众号 appid。"""
    if scene == 'mini':
        return settings.WXPAY_MINI_APPID or settings.WXPAY_APPID
    return settings.WXPAY_APPID or settings.WXPAY_MINI_APPID


# ------------------------------------------------------------------------- 下单
def _order_body(out_trade_no: str, description: str, amount_cents: int,
                trade_type: str, scene: str, openid: str, client_ip: str) -> dict:
    body = {
        'appid': _appid(trade_type, scene),
        'mchid': settings.WXPAY_MCHID,
        'description': description[:127],
        'out_trade_no': out_trade_no,
        'notify_url': settings.WXPAY_NOTIFY_URL,
        'amount': {'total': int(amount_cents), 'currency': 'CNY'},
    }
    if trade_type == TRADE_JSAPI:
        if not openid:
            raise WeChatPayError('JSAPI 支付缺少 openid')
        body['payer'] = {'openid': openid}
    elif trade_type == TRADE_H5:
        body['scene_info'] = {
            'payer_client_ip': client_ip or '127.0.0.1',
            'h5_info': {'type': 'Wap'},
        }
    # H5 支付允许带 redirect_url，支付完成后跳回前端继续轮询订单
    if trade_type == TRADE_H5 and settings.WXPAY_H5_REDIRECT_URL:
        body['scene_info']['h5_info']['wap_url'] = settings.WXPAY_H5_REDIRECT_URL
        body['scene_info']['h5_info']['wap_name'] = '家庭财务通'
    return body


def jsapi_prepay(out_trade_no: str, description: str, amount_cents: int,
                 openid: str, scene: str = '') -> str:
    """JSAPI 下单（公众号 / 小程序），返回 prepay_id。"""
    body = _order_body(out_trade_no, description, amount_cents, TRADE_JSAPI,
                       scene, openid, '')
    return _request('POST', PATH_JSAPI, body).get('prepay_id', '')


def h5_prepay(out_trade_no: str, description: str, amount_cents: int,
              client_ip: str = '') -> str:
    """H5 下单（微信外浏览器），返回 mweb_url，前端直接跳转即可。"""
    body = _order_body(out_trade_no, description, amount_cents, TRADE_H5,
                       '', '', client_ip)
    return _request('POST', PATH_H5, body).get('h5_url', '')


def build_pay_params(prepay_id: str, scene: str = '') -> dict:
    """用 prepay_id 二次签名，得到前端调起支付的参数（公众号与小程序通用）。"""
    if not prepay_id:
        raise WeChatPayError('prepay_id 为空，无法调起支付')
    appid = _appid(TRADE_JSAPI, scene)
    timestamp = str(int(time.time()))
    nonce = _nonce()
    package = f'prepay_id={prepay_id}'
    message = f'{appid}\n{timestamp}\n{nonce}\n{package}\n'
    return {
        'appId': appid,
        'timeStamp': timestamp,
        'nonceStr': nonce,
        'package': package,
        'signType': 'RSA',
        'paySign': _rsa_sign(message),
    }


def query_order(out_trade_no: str) -> dict:
    """按商户订单号查单，返回微信侧的订单数据。"""
    path = f'/v3/pay/transactions/out-trade-no/{out_trade_no}?mchid={settings.WXPAY_MCHID}'
    return _request('GET', path)


def close_order(out_trade_no: str) -> bool:
    """关闭订单（超时未付 / 用户放弃）。"""
    path = f'/v3/pay/transactions/out-trade-no/{out_trade_no}/close'
    try:
        _request('POST', path, {'mchid': settings.WXPAY_MCHID})
    except WeChatPayError:
        logger.warning('关单失败 out_trade_no=%s', out_trade_no)
        return False
    return True


# ------------------------------------------------------------------------- 回调
def _platform_cert(serial_no: str):
    """取平台证书（验回调签名用）：内存 → 本地缓存目录 → 在线下载。"""
    _, _, _, _, x509 = _crypto()
    if serial_no not in _platform_certs:
        _load_cached_certs()
    if serial_no not in _platform_certs:
        _download_platform_certs()
    cert = _platform_certs.get(serial_no)
    if cert is None:
        raise WeChatPayError('未找到微信支付平台证书，无法验签')
    return cert


def _cert_dir() -> Path:
    path = Path(settings.WXPAY_CERT_DIR)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _load_cached_certs() -> None:
    _, _, _, _, x509 = _crypto()
    for pem_file in _cert_dir().glob('*.pem'):
        try:
            cert = x509.load_pem_x509_certificate(pem_file.read_bytes())
        except Exception:
            continue
        _platform_certs[_serial_of(cert)] = cert


def _serial_of(cert) -> str:
    return format(cert.serial_number, 'X').upper()


def _download_platform_certs() -> None:
    """从 /v3/certificates 下载平台证书，用 API v3 密钥解密后落盘缓存。"""
    _, _, _, AESGCM, x509 = _crypto()
    data = _request('GET', '/v3/certificates')
    key = settings.WXPAY_API_V3_KEY.encode('utf-8')
    for item in data.get('data') or []:
        enc = item.get('encrypt_certificate') or {}
        try:
            pem = AESGCM(key).decrypt(enc['nonce'].encode('utf-8'),
                                      base64.b64decode(enc['ciphertext']),
                                      enc['associated_data'].encode('utf-8'))
            cert = x509.load_pem_x509_certificate(pem)
        except Exception as exc:
            logger.warning('平台证书解密失败 serial=%s: %s', item.get('serial_no'), exc)
            continue
        serial = _serial_of(cert)
        (_cert_dir() / f'{serial}.pem').write_bytes(pem)
        _platform_certs[serial] = cert


def _verify_signature(cert, message: str, signature: str) -> None:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding

    try:
        cert.public_key().verify(base64.b64decode(signature), message.encode('utf-8'),
                                 padding.PKCS1v15(), hashes.SHA256())
    except Exception as exc:
        raise WeChatPayError('微信支付回调签名校验失败') from exc


def parse_notify(headers, body: bytes) -> dict:
    """校验回调签名并用 API v3 密钥解密 resource，返回解密后的支付结果。"""
    def header(name: str) -> str:
        # Django 的 headers 支持大小写不敏感取值
        try:
            return headers.get(name) or ''
        except Exception:
            return ''

    serial = header('Wechatpay-Serial')
    signature = header('Wechatpay-Signature')
    timestamp = header('Wechatpay-Timestamp')
    nonce = header('Wechatpay-Nonce')
    if not (serial and signature):
        raise WeChatPayError('回调缺少验签头')

    text = body.decode('utf-8') if isinstance(body, (bytes, bytearray)) else str(body)
    _verify_signature(_platform_cert(serial), f'{timestamp}\n{nonce}\n{text}\n', signature)

    _, _, _, AESGCM, _ = _crypto()
    resource = json.loads(text).get('resource') or {}
    try:
        plain = AESGCM(settings.WXPAY_API_V3_KEY.encode('utf-8')).decrypt(
            resource['nonce'].encode('utf-8'),
            base64.b64decode(resource['ciphertext']),
            resource['associated_data'].encode('utf-8'),
        )
    except Exception as exc:
        raise WeChatPayError('回调内容解密失败') from exc
    return json.loads(plain.decode('utf-8'))


# ------------------------------------------------------------------------- 鉴权取 openid
def jscode2session(code: str) -> str:
    """小程序：wx.login 的 code 换 openid。"""
    appid = settings.WXPAY_MINI_APPID or settings.WXPAY_APPID
    secret = settings.WXPAY_MINI_SECRET
    if not (appid and secret):
        raise WeChatPayError('未配置小程序 appid / secret')
    data = _wechat_get('https://api.weixin.qq.com/sns/jscode2session', {
        'appid': appid, 'secret': secret, 'js_code': code,
        'grant_type': 'authorization_code',
    })
    return data.get('openid') or ''


def oauth_openid(code: str) -> str:
    """公众号网页授权：code 换 openid（snsapi_base 静默授权）。"""
    if not (settings.WXPAY_APPID and settings.WXPAY_APP_SECRET):
        raise WeChatPayError('未配置公众号 appid / secret')
    data = _wechat_get('https://api.weixin.qq.com/sns/oauth2/access_token', {
        'appid': settings.WXPAY_APPID, 'secret': settings.WXPAY_APP_SECRET,
        'code': code, 'grant_type': 'authorization_code',
    })
    return data.get('openid') or ''


def _wechat_get(url: str, params: dict) -> dict:
    try:
        resp = httpx.get(url, params=params, timeout=settings.WXPAY_TIMEOUT)
        data = resp.json()
    except Exception as exc:
        raise WeChatPayError(f'微信接口请求失败：{exc}') from exc
    errcode = data.get('errcode')
    if errcode:
        raise WeChatPayError(data.get('errmsg') or f'微信接口返回错误 {errcode}')
    return data
