from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger, AstrBotConfig
import time

@register("astrbot_plugin_speedometer", "AstrBot-Assistant", "提供测速与周回计算功能。使用 /cs 开始或记录时间点，返回与上次记录的时间差及每小时周回数；使用 /cse 停止并返回所有记录的总结报告。", "1.0.0", "https://github.com/yourname/astrbot_plugin_speedometer")
class SpeedometerPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        # 用于存储会话状态：{session_id: {"last_time": float, "records": list, "start_timestamp": float}}
        self.sessions = {}

    def _get_session_data(self, session_id: str):
        """获取或初始化会话数据"""
        # 检查是否超过配置的自动重置超时时间
        timeout = self.config.get("session_timeout", 3600)
        current_now = time.time()
        
        if session_id in self.sessions:
            last_activity = self.sessions[session_id].get("last_time", 0)
            if timeout > 0 and (current_now - last_activity) > timeout:
                logger.info(f"Session {session_id} timed out, resetting.")
                del self.sessions[session_id]

        if session_id not in self.sessions:
            self.sessions[session_id] = {
                "last_time": 0.0,
                "records": [],
                "start_timestamp": 0.0
            }
        return self.sessions[session_id]

    def _format_duration(self, seconds: float) -> str:
        """格式化秒数为 分:秒"""
        m, s = divmod(int(seconds), 60)
        return f"{m}分{s}秒"

    @filter.command("cs")
    async def record_speed(self, event: AstrMessageEvent):
        """记录当前时间点，并计算与上次记录的间隔时间及周回数。"""
        session_id = event.message_obj.session_id
        session = self._get_session_data(session_id)
        now = time.time()
        
        # 获取配置
        unit_settings = self.config.get("unit_settings", {})
        precision = unit_settings.get("round_precision", 1)
        show_ts = unit_settings.get("show_timestamp", True)
        max_records = self.config.get("max_records_per_session", 100)
        custom_prompts = self.config.get("custom_prompts", {})
        
        # 首次记录逻辑
        if session["last_time"] == 0.0:
            session["last_time"] = now
            session["start_timestamp"] = now
            start_msg = custom_prompts.get("start_msg", "测速开始！已记录起始时间点。")
            yield event.plain_result(start_msg)
            return

        # 检查记录上限
        if len(session["records"]) >= max_records:
            yield event.plain_result(f"已达到单次最大记录数({max_records})，请发送 /cse 查看报告并重置。")
            return

        # 计算差异
        diff = now - session["last_time"]
        session["records"].append(diff)
        
        # 计算周回 (每小时完成次数)
        # Formula: 3600 / seconds
        laps_per_hour = round(3600 / diff, precision) if diff > 0 else 0
        
        # 格式化时间戳显示
        ts_str = ""
        if show_ts:
            local_time = time.strftime("%H:%M:%S", time.localtime(now))
            ts_str = f"\n(当前记录时间 {local_time})"

        response = (
            f"🤖 第 {len(session['records'])} 次记录成功！\n"
            f"⏱️ 间隔耗时：{self._format_duration(diff)}\n"
            f"🔄 当前周回：{laps_per_hour} 次/小时"
            f"{ts_str}"
        )
        
        session["last_time"] = now # 更新最后一次记录时间
        yield event.plain_result(response)

    @filter.command("cse")
    async def end_speed(self, event: AstrMessageEvent):
        """停止记录并输出本次测速的所有历史统计总结。"""
        session_id = event.message_obj.session_id
        if session_id not in self.sessions or not self.sessions[session_id]["records"]:
            yield event.plain_result("当前没有正在进行的测速会话。发送 /cs 开始计时。")
            return

        session = self.sessions[session_id]
        records = session["records"]
        
        total_count = len(records)
        total_time = sum(records)
        avg_time = total_time / total_count
        fastest = min(records)
        slowest = max(records)
        
        custom_prompts = self.config.get("custom_prompts", {})
        stop_title = custom_prompts.get("stop_msg", "测速已停止。本次统计报告：")
        report_style = self.config.get("report_style", "text")

        if report_style == "markdown":
            report = (
                f"### {stop_title}\n\n"
                f"* **总计次数**：{total_count} 次\n"
                f"* **平均耗时**：{self._format_duration(avg_time)}\n"
                f"* **最快纪录**：{self._format_duration(fastest)}\n"
                f"* **最慢纪录**：{self._format_duration(slowest)}\n\n"
                f"🏁 *状态：已重置，发送 /cs 可重新开始。*"
            )
        else:
            report = (
                f"🤖 {stop_title}\n"
                f"📊 总计次数：{total_count} 次\n"
                f"⏳ 平均耗时：{self._format_duration(avg_time)}\n"
                f"⚡ 最快纪录：{self._format_duration(fastest)}\n"
                f"🐢 最慢纪录：{self._format_duration(slowest)}\n"
                f"🏁 状态：已重置，发送 /cs 可重新开始。"
            )

        # 清除会话数据
        del self.sessions[session_id]
        yield event.plain_result(report)

    async def terminate(self):
        """插件卸载时清理内存"""
        self.sessions.clear()
        logger.info("SpeedometerPlugin terminated and memory cleared.")