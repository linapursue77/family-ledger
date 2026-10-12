# -*- coding: utf-8 -*-
"""密码强度校验器。

注册在 settings.AUTH_PASSWORD_VALIDATORS 里，凡是调 validate_password() 的地方
（注册 / 短信找回 / 设置密码 / 修改密码）都会自动生效，规则永远只有一份。
"""
from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _


class LetterAndDigitValidator:
    """密码必须同时包含字母和数字。

    Django 内置的 NumericPasswordValidator 只挡「纯数字」，纯字母照样通过，
    所以这里补上业务要求的组合规则。
    """

    code = 'password_no_letter_digit'

    def validate(self, password, user=None):
        # 用 isascii() 限定英文字母：中文字符的 isalpha() 也是 True，
        # 但「密码含中文」不该算满足字母要求，也避免绕开规则
        has_letter = any(ch.isascii() and ch.isalpha() for ch in password)
        has_digit = any(ch.isdigit() for ch in password)

        if not has_letter and not has_digit:
            raise ValidationError(
                _('密码必须包含字母和数字'), code=self.code)
        if not has_letter:
            raise ValidationError(
                _('密码还需包含字母，不能只有数字'), code=self.code)
        if not has_digit:
            raise ValidationError(
                _('密码还需包含数字，不能只有字母'), code=self.code)

    def get_help_text(self):
        return _('密码需同时包含字母和数字，长度不低于 6 位')
