# -*- coding: utf-8 -*-
"""
短信发送：默认 mock（通过 logging 写入 platform_*.log，与 run_mac.sh 后台运行一致）。
生产环境可替换为阿里云/腾讯云等，见 README。
"""
import logging
import random
import string

from config import SMS_PROVIDER, SMS_CODE_LENGTH


def generate_code(length=None):
    length = length or SMS_CODE_LENGTH
    return "".join(random.choices(string.digits, k=length))


def send_verification_code(phone: str, code: str) -> bool:
    """发送验证码。返回是否发送成功。"""
    if SMS_PROVIDER == "mock" or not SMS_PROVIDER:
        # 必须用 root logger：Flask 对名为「app」的包 logger 常设 propagate=False，
        # app.sms 的日志到不了挂在 root 上的 DailyPlatformFileHandler。
        logging.getLogger().info("[SMS Mock] 手机号: %s, 验证码: %s", phone, code)
        return True
    # 可在此接入阿里云/腾讯云等，例如：
    # return send_aliyun_sms(phone, code)
    return False


def send_sms(phone: str, code: str) -> bool:
    return send_verification_code(phone, code)
