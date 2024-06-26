from lemonyBot import Plugin, cqcode, Bot
from . import gacha, operator_lib

import re
import os
import atexit
import copy
import logging
import asyncio
import traceback

import yaml

# 等待注入
request = None


DEFAULT_CONFIG = {
    #
    "enable": {}  # group_id: bool
}
config: dict = None
config_file = "./plugin_configs/arkgacha.yaml"

stat: dict = None  # uid: {star: counter}
stat_file = "./data/arkgacha_stat.yaml"

stat_total: dict = None  # star: counter
stat_total_file = "./data/arkgacha_stat_total.yaml"

gacha_combo = {
    # uid: {pool: counter}
}


def load_all():
    global config
    global stat
    global stat_total
    if os.path.exists(stat_file):
        stat = yaml.load(open(stat_file, "r", encoding="utf-8"), yaml.SafeLoader)
    else:
        stat = {}
    if os.path.exists(stat_total_file):
        stat_total = yaml.load(
            open(stat_total_file, "r", encoding="utf-8"), yaml.SafeLoader
        )
    elif stat:
        total = {k: 0 for k in range(3, 6 + 1)}
        # stat = copy.deepcopy(stat)
        for d in stat.values():
            for star, counter in d.items():
                total[star] += counter
        stat_total = total
    else:
        stat_total = {k: 0 for k in range(3, 6 + 1)}
    if os.path.exists(config_file):
        config = yaml.load(open(config_file, "r", encoding="utf-8"), yaml.SafeLoader)
    else:
        config = copy.deepcopy(DEFAULT_CONFIG)
        yaml.dump(
            DEFAULT_CONFIG,
            open(config_file, "w+", encoding="utf-8"),
            yaml.SafeDumper,
            default_flow_style=False,
            allow_unicode=True,
        )


@atexit.register
def save_all():
    # stat = copy.deepcopy(stat)
    # config = copy.deepcopy(config)
    yaml.dump(
        stat,
        open(stat_file, "w+", encoding="utf-8"),
        yaml.SafeDumper,
        default_flow_style=False,
        allow_unicode=True,
    )
    yaml.dump(
        stat_total,
        open(stat_total_file, "w+", encoding="utf-8"),
        yaml.SafeDumper,
        default_flow_style=False,
        allow_unicode=True,
    )
    yaml.dump(
        config,
        open(config_file, "w+", encoding="utf-8"),
        yaml.SafeDumper,
        default_flow_style=False,
        allow_unicode=True,
    )


load_all()


class ArknightsGacha(Plugin):
    COMMAND_REGEX = r"^\/arkgacha\s+(on|off|help|pstat|astat|refresh|clear)\s*$"
    GACHA_REGEX = r"^(\/arkgacha(\s*10)?|((明日)?方)?舟\s*(标准池?|常驻池?|中坚池?)?\s*(十连抽?|单抽|抽卡))\s*$"

    def __init__(self, bot: Bot):
        super().__init__(bot)
        self.bot: Bot
        self.__inject()
        self.bot.add_task(self.init())

    def __inject(self):
        global request
        request = operator_lib.request = self.bot.request

    async def init(self):
        logging.info("load operator library in 2s")
        await asyncio.sleep(2)
        gacha.init()
        logging.info("operator library loaded ok")

    def message_group_normal(self, event: dict):
        msg: int = event["message"]
        group_id: int = event["group_id"]
        if str(group_id) not in config["enable"]:
            config["enable"][str(group_id)] = False
        if params := re.findall(ArknightsGacha.COMMAND_REGEX, msg, re.I):
            command = params[0].lower()
            self.command_trigger(event, command)
        elif params := re.findall(ArknightsGacha.GACHA_REGEX, msg, re.I):
            _, tenfold, _, _, pool, amount = params[0]
            amount = 10 if (("十连" in amount) or tenfold) else 1
            pool = "中坚寻访" if "中坚" in pool else "标准寻访"
            self.gacha_trigger(amount, pool, event)

    def gacha_trigger(self, amount: int, pool: str, event: dict):
        global gacha_combo
        msg_id: int = event["message_id"]
        group_id: int = event["group_id"]
        sender: dict = event["sender"]
        uid: int = sender["user_id"]
        admins: list = self.bot.config.get("admins", [])
        # 检查开关
        if not ((config.get("enable", {}).get(str(group_id), False)) or uid in admins):
            # self.send_group_msg_func(
            #     {
            #         "group_id": group_id,
            #         "message": cqcode.reply(msg_id=msg_id)
            #         + "本群的方舟抽卡模块已被管理员关闭 :(",
            #         "auto_escape": False,
            #     }
            # )
            return
        # 读取计数器
        if str(uid) not in gacha_combo:
            gacha_combo[str(uid)] = {}
        if pool not in gacha_combo[str(uid)]:
            gacha_combo[str(uid)][pool] = 1
        combo = gacha_combo[str(uid)][pool]
        # 选池子
        gacha_gen = {
            "中坚寻访": gacha.gacha_backbone,
            "标准寻访": gacha.gacha_standard,
        }[pool]
        # 开抽
        result = []
        for i in range(amount):
            pack = gacha_gen(combo)
            if pack["star"] == 6:
                combo = 1
            else:
                combo += 1
            result += [pack]
        gacha_combo[str(uid)][pool] = combo
        # 汇报
        msg = "你在 %s 抽了 %d 抽：\n" % (pool, amount)
        msg += "\n".join(
            [
                "{0:{1}<6} ".format("★" * i["star"], chr(12288)) + i["name"]
                for i in result
            ]
        )
        self.send_group_msg_func(
            {
                "group_id": group_id,
                "message": cqcode.reply(msg_id=msg_id) + msg,
                "auto_escape": False,
            }
        )
        # 统计
        if str(uid) not in stat:
            stat[str(uid)] = {k: 0 for k in range(3, 6 + 1)}
        for pack in result:
            stat[str(uid)][pack["star"]] += 1
            stat_total[pack["star"]] += 1

        save_all()

    def command_trigger(self, event: dict, command: str):
        global config
        group_id: int = event["group_id"]
        status = config["enable"].get(str(group_id), False)
        sender: dict = event["sender"]
        uid: int = sender["user_id"]
        reply = lambda t: self.send_group_msg_func(
            {
                "group_id": group_id,
                "message": cqcode.reply(msg_id=event["message_id"]) + t,
                "auto_escape": False,
            }
        )
        success_reply = lambda s: self.send_group_msg_func(
            {
                "group_id": group_id,
                "message": cqcode.reply(msg_id=event["message_id"])
                + "方舟抽卡开关已设为 %s" % s,
                "auto_escape": False,
            }
        )
        skipp_reply = lambda s: self.send_group_msg_func(
            {
                "group_id": group_id,
                "message": cqcode.reply(msg_id=event["message_id"])
                + "方舟抽卡开关状态已经是 %s 了" % s,
                "auto_escape": False,
            }
        )
        send = lambda t: self.send_group_msg_func(
            {
                "group_id": group_id,
                "message": t,
                "auto_escape": False,
            }
        )
        check_perm = lambda sender_: sender_.get("user_id") in self.bot.config.get(
            "admins", []
        ) or sender_.get("role") in ["admin", "owner"]
        match command:
            case "on" | "off":
                if not check_perm(sender):
                    reply("permisson denied")
                    return
                new_status = not status
                if status == {"on": True, "off": False}[command]:
                    skipp_reply(status)
                else:
                    config["enable"][str(group_id)] = new_status
                    success_reply(new_status)
            case "help":
                send(
                    """方舟抽卡模块帮助
直接发送 /arkgacha 或 明日方舟十连/抽卡 以抽卡
/arkgacha on/off - 在本群开启/关闭本模块
/arkgacha astat/pstat - 查看全体/个人统计
/arkgacha refresh - 更新到最新的干员列表
/arkgacha clear - 清除自己的抽卡统计和连续抽卡次数
*每次重启的时候连续抽卡次数会重置"""
                )
            case "astat":
                self.bot.add_task(self.show_all_stat(event))
            case "pstat":
                self.bot.add_task(self.show_personal_stat(event))
            case "refresh":
                if uid not in self.admins:
                    reply("permisson denied")
                else:
                    reply("正在刷新干员列表...")
                    self.bot.add_task(self.refresh_list(event))
            case "clear":
                self.bot.add_task(self.clear_stat_combo(event))

    async def clear_stat_combo(self, event):
        global stat
        global gacha_combo
        group_id: int = event["group_id"]
        sender: dict = event["sender"]
        uid: int = sender["user_id"]
        stat.pop(str(uid), None)
        gacha_combo.pop(str(uid), None)

        self.send_group_msg_func(
            {
                "group_id": group_id,
                "message": cqcode.reply(msg_id=event["message_id"]) + "success",
                "auto_escape": False,
            }
        )

        save_all()

    async def show_all_stat(self, event):
        group_id: int = event["group_id"]
        total = sum([i for i in stat_total.values()])
        text = """明日方舟抽卡模块状态
在此群的开关状态: %s
""" % (
            config["enable"].get(str(group_id), False)
        )
        if total:
            text += """Bot 总共产出了 %d 抽, 其中: \n%s""" % (
                total,
                "\n".join(
                    [
                        "%d 星: %d 个 (%.2f%%)" % (k, v, v / total * 100)
                        for k, v in stat_total.items()
                    ]
                ),
            )
        else:
            text += "还没有产出记录"
        self.send_group_msg_func(
            {
                "group_id": group_id,
                "message": text,
                "auto_escape": False,
            }
        )

    async def show_personal_stat(self, event):
        group_id: int = event["group_id"]
        sender: dict = event["sender"]
        uid: int = sender["user_id"]
        # stat = copy.deepcopy(stat)
        if str(uid) not in stat:
            self.send_group_msg_func(
                {
                    "group_id": group_id,
                    "message": cqcode.reply(msg_id=event["message_id"])
                    + "还没有你的抽卡数据噢",
                    "auto_escape": False,
                }
            )
            return
        total = max(sum([i for i in stat[str(uid)].values()]), 1)
        text = (
            "你抽到过: \n"
            + "\n".join(
                [
                    "%d 星: %d 个 (%.2f%%)" % (k, v, v / total * 100)
                    for k, v in stat.get(str(uid), {}).items()
                ]
            )
            + "\n共计 %d 抽, 相当于 %g 合成玉" % (total, total * 600)
        )
        self.send_group_msg_func(
            {
                "group_id": group_id,
                "message": cqcode.reply(msg_id=event["message_id"]) + text,
                "auto_escape": False,
            }
        )

    async def refresh_list(self, event: dict):
        group_id: int = event["group_id"]
        try:
            data = await operator_lib.fetch()
        except Exception as e:
            logging.exception(e)
            self.send_group_msg_func(
                {
                    "group_id": group_id,
                    "message": cqcode.reply(msg_id=event["message_id"])
                    + "刷新失败: \n"
                    + traceback.format_exc(),
                    "auto_escape": False,
                }
            )
        else:
            old_length = len(operator_lib.operator_lib)
            operator_lib.operator_lib = data
            operator_lib.save_lib()
            gacha.init()
            self.send_group_msg_func(
                {
                    "group_id": group_id,
                    "message": cqcode.reply(msg_id=event["message_id"])
                    + "刷新完成，新增了 %d 个干员的数据"
                    % (len(operator_lib.operator_lib) - old_length),
                    "auto_escape": False,
                }
            )
