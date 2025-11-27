'''
Author: Vincent Young, jiajiu123()
Date: 2023-03-30 00:15:22
LastEditors: Vincent Young
LastEditTime: 2023-03-30 02:40:33
FilePath: /fuckZHS/push.py
Telegram: https://t.me/missuo(Vincent Young)

Copyright © 2023 by Vincent, All Rights Reserved. 

保留原作者信息,由@zsyeh进行简单修补
zsyeh7286@gmail.com
'''

import os
import requests
import smtplib
from email.mime.text import MIMEText
from email.header import Header
from dotenv import load_dotenv # 引入 dotenv 以便单独测试时加载配置
  # 新增
import socket # 新增
def pushpluser(title: str, content, token: str) -> None:
    """
    PushPlus 推送
    """
    try:
        requests.get(
            f"http://www.pushplus.plus/send?token={token}&title={title}&content={content}", timeout=10)
    except Exception as e:
        print(f"[PushPlus] 推送失败: {e}")


def barkpusher(title: str, content, token: str) -> None:
    """
    Bark 推送
    """
    try:
        requests.get(f"{token}/{title}/{content}", timeout=10)
    except Exception as e:
        print(f"[Bark] 推送失败: {e}")


def email_notification(subject: str, content: str) -> None:
    """
    SMTP 邮件推送
    自动读取环境变量: SMTP_SERVER, SMTP_PORT, SMTP_SENDER, SMTP_PASSWORD, SMTP_RECEIVER
    """
    # 从环境变量获取配置
    smtp_server = os.getenv("SMTP_SERVER")
    smtp_port = os.getenv("SMTP_PORT")
    sender = os.getenv("SMTP_SENDER")
    password = os.getenv("SMTP_PASSWORD")
    receiver = os.getenv("SMTP_RECEIVER")

    # 检查配置完整性
    if not all([smtp_server, smtp_port, sender, password, receiver]):
        print("[Push] 邮件推送跳过: 环境变量配置不完整 (请检查 .env 文件)")
        return
    
    # === 在这里插入代理补丁 (假设您的代理是本地 7890) ===
    # 注意：这会影响全局 socket，如果您的脚本其他部分不需要代理可能会有影响
    # 建议仅在连 Gmail 前设置，连完后 unset
    socks.set_default_proxy(socks.SOCKS5, "127.0.0.1", 7890)
    socket.socket = socks.socksocket
    # =================================================
    try:
        # 构建邮件
        message = MIMEText(content, 'plain', 'utf-8')
        message['From'] = sender
        message['To'] = receiver
        message['Subject'] = Header(subject, 'utf-8')

        # 连接服务器
        # 端口 465 通常用于 SSL (Gmail, QQ等推荐)
        if int(smtp_port) == 465:
            server = smtplib.SMTP_SSL(smtp_server, int(smtp_port))
        else:
            # 端口 25 或 587 通常用于 TLS 或 无加密
            server = smtplib.SMTP(smtp_server, int(smtp_port))
            # 尝试启动 TLS，如果服务器支持
            try:
                server.starttls()
            except Exception:
                pass

        # 登录并发送
        server.login(sender, password)
        server.sendmail(sender, [receiver], message.as_string())
        server.quit()
        print(f"[Push] 邮件已发送至 {receiver}: {subject}")

    except smtplib.SMTPAuthenticationError:
        print("[Push] 邮件发送失败: 认证错误 (请检查邮箱账号或授权码)")
    except Exception as e:
        print(f"[Push] 邮件发送失败: {e}")

# ==========================================
# 独立运行测试模块
# 运行方式: python push.py
# ==========================================
if __name__ == "__main__":
    # 1. 加载环境变量
    print("正在加载 .env 配置...")
    load_dotenv()

    print("="*40)
    print("Push 服务独立测试工具")
    print("="*40)

    # 2. 检查配置
    smtp_server = os.getenv("SMTP_SERVER")
    sender = os.getenv("SMTP_SENDER")
    
    if not smtp_server:
        print("[错误] 未读取到 SMTP_SERVER。")
        print("请确保当前目录下存在 .env 文件，且内容正确。")
    else:
        print(f"配置检测:")
        print(f"  - Server: {smtp_server}")
        print(f"  - Port:   {os.getenv('SMTP_PORT')}")
        print(f"  - Sender: {sender}")
        print("-" * 40)
        print("正在发送测试邮件...")

        # 3. 执行发送
        test_subject = "【脚本测试】邮件配置验证成功"
        test_content = (
            "恭喜！\n\n"
            "这是一封来自 fuckZHS 脚本的测试邮件。\n"
            "如果您收到了这封邮件，说明您的 SMTP 配置 (Host/Port/User/Pass) 完全正确。\n\n"
            "您现在可以放心地运行主程序 main.py 了。"
        )
        
        email_notification(test_subject, test_content)

    print("="*40)
    print("测试结束")