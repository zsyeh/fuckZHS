import os
import sys
import json
import time
import argparse
import platform
import threading
import http.server
import socketserver
import datetime
from functools import partial
from contextlib import suppress
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 本地模块导入
from fucker import Fucker
from logger import logger
from ObjDict import ObjDict
from utils import showImage, cookie_jar_to_list, getConfigPath, getRealPath, versionCmp
from push import email_notification

# ==========================================
# 辅助类定义
# ==========================================

class NotificationManager:
    """
    通知管理器：负责根据配置的精细度发送通知和心跳包
    """
    def __init__(self):
        # 默认 ROUGH，除非显式设置为 DEBUG
        self.level = os.getenv("REPORT_LEVEL", "ROUGH").upper()
        self.heartbeat_thread = None
        self.keep_running = False
        self.start_time = datetime.datetime.now()

    def send(self, subject, content, force=False):
        """
        发送通知的主入口
        :param force: 如果为 True，无论什么级别都发送 (用于报错、结束等关键节点)
        """
        # 如果是 ROUGH 模式，且不是强制发送的消息，则忽略
        if self.level == "ROUGH" and not force:
            return
        
        # 调用 push.py 的发送逻辑
        email_notification(subject, content)

    def start_heartbeat(self):
        """开启每分钟的心跳报告 (仅 DEBUG 模式)"""
        if self.level != "DEBUG":
            return

        self.keep_running = True
        self.heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
        self.heartbeat_thread.start()
        print("[System] Debug模式已开启：心跳线程已启动 (60s/次)")

    def stop_heartbeat(self):
        """停止心跳"""
        self.keep_running = False
        if self.heartbeat_thread and self.heartbeat_thread.is_alive():
            self.heartbeat_thread.join(timeout=2)

    def _heartbeat_loop(self):
        while self.keep_running:
            # 等待 60 秒
            for _ in range(60):
                if not self.keep_running: return
                time.sleep(1)
            
            # 发送心跳
            duration = datetime.datetime.now() - self.start_time
            msg = f"脚本正在运行中...\n已运行时间: {str(duration).split('.')[0]}\n当前时间: {datetime.datetime.now().strftime('%H:%M:%S')}"
            print(f"[Heartbeat] 发送运行报告...")
            # 心跳属于 DEBUG 级别的消息，不强制
            self.send("【脚本心跳】运行正常", msg, force=False)


class QRServerHandler:
    """
    封装二维码 Web 服务器逻辑
    """
    def __init__(self, port=8000):
        self.port = port
        self.server = None
        self.thread = None

    def show_qr_via_web(self, img):
        filename = "qrcode.png"
        try:
            if isinstance(img, bytes):
                with open(filename, 'wb') as f:
                    f.write(img)
            elif hasattr(img, 'save'):
                img.save(filename)
            else:
                return
        except Exception:
            return

        # 如果服务未启动，则启动
        if self.server is None:
            self.thread = threading.Thread(target=self._run_server, args=(filename,), daemon=True)
            self.thread.start()
        else:
            # 图片已更新，无需重启服务
            pass

    def _run_server(self, filename):
        try:
            socketserver.TCPServer.allow_reuse_address = True
            Handler = http.server.SimpleHTTPRequestHandler
            Handler.log_message = lambda *args: None
            
            self.server = socketserver.TCPServer(("", self.port), Handler)
            print(f"\n{'='*50}")
            print(f"[Web服务已启动] 请在浏览器打开扫码: http://localhost:{self.port}/{filename}")
            print(f"{'='*50}\n")
            self.server.serve_forever()
        except OSError as e:
            if e.errno == 98 or "Address already in use" in str(e):
                print(f"[提示] 端口 {self.port} 被占用，请手动查看 qrcode.png")
            else:
                print(f"Web服务器启动失败: {e}")
        finally:
            if self.server:
                self.server.server_close()

    def stop(self):
        if self.server:
            print("\n[Web服务] 登录成功，正在关闭二维码服务器...")
            self.server.shutdown()
            self.server.server_close()
            self.server = None


# ==========================================
# 主程序逻辑
# ==========================================

DEFAULT_CONFIG = {
    "username": "",
    "password": "",
    "qrlogin": True,
    "save_cookies": True,
    "proxies": {},
    "logLevel": "INFO",
    "tree_view": True,
    "progressbar_view": True,
    "qr_extra": {"show_in_terminal": None, "ensure_unicode": False},
    "image_path": "",
    "pushplus": {"enable": False, "token": ""},
    "bark": {"enable": False, "token": "https://example.com/xxxxxxxxx"},
    "config_version": "1.4.0",
    "ai": {
        "enabled": True, "use_zhidao_ai": True, "use_stream": True,
        "openai": {"api_base": "https://api.openai.com", "api_key": "sk-", "model_name": "claude-3-5-sonnet-20240620"},
        "ppt_processing": {"provide_to_ai": False, "moonShot": {"base_url": "https://api.moonshot.cn/v1", "api_key": "sk-", "delete_after_convert": True}}
    }
}

def load_and_update_config():
    """加载并更新配置文件"""
    config_path = getConfigPath()
    if os.path.isfile(config_path):
        with open(config_path, 'r+', encoding="UTF-8") as f:
            config = ObjDict(json.load(f), default=None)
            if "config_version" not in config:
                config.config_version = "1.0.0"
            if versionCmp(config.config_version, DEFAULT_CONFIG["config_version"]) < 0:
                # 简单的版本迁移逻辑
                new = ObjDict(DEFAULT_CONFIG, default=None)
                if versionCmp(config.config_version, "1.0.1") < 0: config.pop("qr_extra", None)
                if versionCmp(config.config_version, "1.3.0") < 0:
                    pushplus = config.pop("push", {})
                    new.pushplus.update(pushplus)
                config.pop("config_version", None)
                new.update(config)
                config = new
                f.seek(0)
                json.dump(config, f, indent=4)
                f.truncate()
                print("****Config file updated****")
            return config
    else:
        config = ObjDict(DEFAULT_CONFIG, default=None)
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=4)
        return config

def parse_args(config):
    """解析命令行参数"""
    parser = argparse.ArgumentParser(prog="ZHS Fucker")
    parser.add_argument("-c", "--course", type=str, nargs="+", help="CourseId")
    parser.add_argument("-v", "--videos", type=str, nargs="+", help="Video IDs")
    parser.add_argument("-u", "--username", type=str, help="Username")
    parser.add_argument("-p", "--password", type=str, help="Password")
    parser.add_argument("-s", "--speed", type=float, help="Video Speed")
    parser.add_argument("-t", "--threshold", type=float, help="Video End Threshold")
    parser.add_argument("-l", "--limit", type=int, default=0, help="Time Limit")
    parser.add_argument("-q", "--qrlogin", action="store_true", help="QR Login")
    parser.add_argument("-d", "--debug", action="store_true", help="Debug Mode")
    parser.add_argument("-f", "--fetch", action="store_true", help="Fetch list")
    parser.add_argument("--show_in_terminal", action="store_true", help="Terminal QR")
    parser.add_argument("--proxy", type=str, help="Proxy Config")
    parser.add_argument("--tree_view", type=bool, help="Tree View")
    parser.add_argument("--progressbar_view", type=bool, help="Progress Bar")
    parser.add_argument("--image_path", type=str, help="Image Path")
    parser.add_argument("-ai", "--aicourse", type=str, nargs=2, metavar=('COURSE_ID', 'CLASS_ID'), help="AI Course")
    parser.add_argument("--noexam", type=bool, help="Disable AI exam")
    
    args = parser.parse_args()
    
    # 参数合并逻辑
    args.username = args.username or config.username
    args.password = args.password or config.password
    args.qrlogin = args.qrlogin or config.qrlogin or True
    args.show_in_terminal = args.show_in_terminal or config.qr_extra.show_in_terminal
    if args.show_in_terminal is None:
        args.show_in_terminal = platform.system() == "Windows"
    
    # 代理处理
    proxies = config.proxies or {}
    if args.proxy:
        scheme = args.proxy.lower().split("://")[0]
        if scheme in ["http", "https"]:
            proxies["http"] = proxies["https"] = args.proxy
        elif scheme == "socks5":
            proxies["socks5"] = args.proxy
        elif scheme == "all":
            proxies["http"] = proxies["https"] = proxies["socks5"] = args.proxy
        else:
            print(f"*Unsupported proxy type: {scheme}")
            sys.exit(1)
            
    return args, proxies

def main():
    # 1. 初始化配置与参数
    config = load_and_update_config()
    args, proxies = parse_args(config)
    
    # 2. 初始化服务组件
    notifier = NotificationManager()
    qr_handler = QRServerHandler()
    
    logger.setLevel("DEBUG" if args.debug else (config.logLevel or "WARNING"))
    if logger.getLevel() == "DEBUG":
        print("DEBUG MODE ENABLED\n")

    # 3. 检查更新 (略微精简逻辑)
    try:
        with open(getRealPath("meta.json"), "r") as f:
            m = ObjDict(json.load(f))
            url = f"https://raw.githubusercontent.com/{m.author}/fuckZHS/{m.branch}/meta.json"
            r = ObjDict(requests.get(url, proxies=proxies, timeout=5).json())
            if versionCmp(m.version, r.version) < 0:
                print(f"New version available: {r.version}")
    except Exception:
        pass

    # 4. 实例化 Fucker
    fucker = Fucker(
        proxies=proxies, 
        speed=args.speed, 
        end_thre=args.threshold, 
        limit=args.limit,
        pushplus_token=config.pushplus.enable and config.pushplus.token or "",
        bark_token=config.bark.enable and config.bark.token or "",
        tree_view=args.tree_view or config.tree_view,
        progressbar_view=args.progressbar_view or config.progressbar_view,
        image_path=args.image_path or config.image_path
    )

    # 5. Cookie 恢复
    cookies_path = getRealPath("./cookies.json")
    cookies_loaded = False
    if config.save_cookies and os.path.exists(cookies_path):
        with open(cookies_path, 'r') as f:
            raw = f.read() or '{}'
        with suppress(Exception):
            fucker.cookies = json.loads(raw)
            # 简单验证 cookie 是否有效
            if fucker.getZhidaoList() or fucker.getHikeList():
                print("Successfully recovered from saved cookies\n")
                cookies_loaded = True

    # 6. 登录流程
    if not cookies_loaded:
        try:
            if args.qrlogin:
                fucker.login(use_qr=True, qr_callback=qr_handler.show_qr_via_web)
            else:
                fucker.login(args.username, args.password)
            
            qr_handler.stop()
            print("Login Successful\n")
            
            if config.save_cookies:
                with open(cookies_path, 'w') as f:
                    json.dump(cookie_jar_to_list(fucker.cookies), f, indent=2, ensure_ascii=False)
        except Exception as e:
            error_msg = str(e)
            print(f"登录失败: {error_msg}")
            # 强制发送，因为这是致命错误
            notifier.send("【脚本警报】登录失败", f"脚本已退出。\n错误: {error_msg}", force=True)
            sys.exit(1)

    # 7. 开始主任务 - 启动心跳
    notifier.start_heartbeat()
    
    try:
        # AI 课程逻辑
        if args.aicourse:
            try:
                # ... (此处省略配置校验逻辑，保持简洁，直接调用)
                fucker.fuckAiCourse(args.aicourse[0], args.aicourse[1], aiConfig=config.ai, no_exam=not args.noexam)
            except Exception as e:
                logger.exception(e)
                notifier.send("【脚本警报】AI课程出错", str(e), force=True)
            finally:
                notifier.send("【脚本通知】AI课程结束", "任务已结束", force=True)
                sys.exit(0)

        # 获取/保存课程列表
        exec_list = getRealPath("execution.json")
        if args.fetch:
            zhidao_ids = [{"name": c.courseName, "id": c.secret} for c in fucker.getZhidaoList()]
            hike_ids = [{"name": c.courseName, "id": str(c.courseId)} for c in fucker.getHikeList()]
            with open(exec_list, "w") as f:
                json.dump(zhidao_ids + hike_ids, f, indent=4, ensure_ascii=False)
            sys.exit(0)

        # 确定待刷课程
        target_courses = args.course
        if not target_courses and os.path.isfile(exec_list):
            with open(exec_list, "r") as f:
                try: target_courses = [str(c["id"]) for c in json.load(f)]
                except: pass
        
        if not target_courses:
            fucker.fuckWhatever()
            notifier.send("【脚本通知】全部完成", "fuckWhatever 模式执行完毕", force=True)
            sys.exit(0)

        # 循环刷课
        for c in list(target_courses):
            # 视频模式
            if args.videos:
                for v in list(args.videos):
                    try:
                        fucker.fuckVideo(course_id=c, video_id=v)
                        print(f"Finished video {v}")
                        args.videos.remove(v)
                    except Exception as e:
                        err = str(e).lower()
                        if "captcha" in err or "验证码" in err:
                            notifier.send("【脚本警报】验证码阻塞", f"视频 {v} 需要验证码", force=True)
            # 课程模式
            else:
                try:
                    fucker.fuckCourse(course_id=c)
                    target_courses.remove(c)
                except Exception as e:
                    logger.exception(e)
                    err = str(e).lower()
                    if "captcha" in err or "验证码" in err:
                        notifier.send("【脚本警报】验证码阻塞", f"课程 {c} 需要验证码", force=True)
                    else:
                        # 普通错误，如果在 ROUGH 模式下，也会被发送，因为这是 Error
                        notifier.send(f"【脚本警报】课程 {c} 出错", str(e), force=True)

        # 最终报告
        if args.videos:
            notifier.send("【脚本报告】有未完成视频", f"失败列表: {args.videos}", force=True)
        else:
            notifier.send("【脚本通知】任务全部完成", "所有指定任务已结束。", force=True)

    except KeyboardInterrupt:
        print("\n用户手动停止")
    finally:
        # 8. 清理资源
        notifier.stop_heartbeat()

if __name__ == "__main__":
    main()