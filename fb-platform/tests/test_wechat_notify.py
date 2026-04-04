# -*- coding: utf-8 -*-
from app.wechat_notify import sign_v2_md5, verify_v2_sign, xml_body_to_dict


def test_xml_body_to_dict():
    xml = """<xml>
<return_code><![CDATA[SUCCESS]]></return_code>
<out_trade_no><![CDATA[FB1]]></out_trade_no>
<total_fee><![CDATA[2990]]></total_fee>
</xml>"""
    d = xml_body_to_dict(xml)
    assert d["return_code"] == "SUCCESS"
    assert d["out_trade_no"] == "FB1"
    assert d["total_fee"] == "2990"


def test_v2_sign_verify_roundtrip():
    api_key = "192006250b4c09247ec02edce69f6a2d"
    params = {
        "appid": "wxd930ea5d5a258f4f",
        "mch_id": "10000100",
        "device_info": "1000",
        "body": "test",
        "nonce_str": "ibuaiVcKdpRxkhJA",
    }
    params["sign"] = sign_v2_md5(params, api_key)
    assert verify_v2_sign(params, api_key)
