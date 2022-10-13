from graia.ariadne.app import Ariadne
from graia.ariadne.event.message import GroupMessage
from graia.ariadne.message.chain import MessageChain
from graia.ariadne.message.element import At,Plain
from graia.ariadne.model import Group, Friend, MiraiSession

from graia.saya import Channel
from graia.saya.builtins.broadcast.schema import ListenerSchema

from graia.scheduler import timers
from graia.scheduler.saya import GraiaSchedulerBehaviour, SchedulerSchema

from graia.ariadne.event.lifecycle import ApplicationLaunched, ApplicationShutdowned

from . import epidemic

from loguru import logger

import re

channel = Channel.current()

channel.name("COVID-19 Epidemic Info Reply")
channel.description("新冠疫情播报姬")
channel.author("NingmengLemon")

match_pattern = re.compile('([\u4e00-\u9fa5]+?)\s*疫情$')

@channel.use(ListenerSchema(listening_events=[GroupMessage]))
async def epidemic_info_reply(app: Ariadne, group: Group, message: MessageChain):
   msg = str(message.include(Plain)).strip().lower()
   if msg.startswith('#'):#At(app.account) in message:
      msg = msg[1:]
      mobj = match_pattern.match(msg)
      if mobj:
         area = mobj.groups()[0]
         await app.sendMessage(
            group,
            MessageChain.create(epidemic.query_text(area=area))
            )

@channel.use(ListenerSchema(listening_events=[ApplicationLaunched]))
@channel.use(SchedulerSchema(timer=timers.every_custom_seconds(1800)))
async def background_task():
   try:
      await epidemic.afetch()
   except Exception as e:
      logger.error('Unable to fetch epidemic data: '+str(e))
   else:
      #logger.info('Fetched epidemic data')
      pass
