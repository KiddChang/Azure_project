from __future__ import unicode_literals
# import correct random packages
import random
import pymysql
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
import configparser
# Audio Message Process packages
import AzurelBotAudioHandler
# MySQL  Processs packages
from linebot.models import MessageEvent, TextMessage, TextSendMessage, AudioMessage, ImageMessage, ImageSendMessage
from pydub import AudioSegment
import azure.cognitiveservices.speech as speechsdk
import jieba.analyse
import re
import time
import matplotlib.pyplot as plt
import cost as c

app = Flask(__name__)
# Azure key
speech_key, service_region = "改成自己的key", "改成自己的地區"
speech_config = speechsdk.SpeechConfig(subscription=speech_key, region=service_region)

# LINE BOT key
config = configparser.ConfigParser()
config.read('config.ini')

# LINE 聊天機器人的基本資料
print(config)
line_bot_api = LineBotApi(config.get('line-bot', 'channel_access_token'))
handler = WebhookHandler(config.get('line-bot', 'channel_secret'))

# MySQL Info (改成自己的 MYSQL 帳戶)
loginInfo = {
    'host': 'localhost',
    'port': 3306,
    'user': 'root',
    'passwd': 'pwd',
    'db': 'azuredata',
    'charset': 'utf8mb4'
}
datetime = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())


# get LINE BOT message from user
@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    app.logger.info("Request body: " + body)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'



# set user basic Info
@handler.add(MessageEvent, message=TextMessage)
def getUserInfo(event):
    if "預算" in event.message.text:
        user_id = event.source.user_id
        user_name = line_bot_api.get_profile(user_id).display_name
        print("user_id =", user_id)

        MAXLIMIT = re.findall('\d+', event.message.text)[0]
        print(event.message.text)
        conn = pymysql.connect(**loginInfo)
        cursor = conn.cursor()
        sql = """INSERT INTO userdata (INDEXNO, CUSTOMERNO, CNAME, MAXLIMIT, COST, DATATIME,CATEGORY)
               VALUES ('{a}', '{b}', '{c}', '{d}', '{e}', '{f}', '{g}');
             """.format(a=1, b=user_id, c=user_name, d=MAXLIMIT, e=0, f=datetime, g=0)
        cursor.execute(sql)
        conn.commit()
        cursor.close()
        conn.close()

        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text='本月預算= ' + str(MAXLIMIT))
        )
    
    elif '清空' in event.message.text:
        conn = pymysql.connect(**loginInfo)
        cursor = conn.cursor()
        cursor.execute('delete from userdata where INDEXNO >= 1;')
        cursor.close()
        conn.close()
        line_bot_api.reply_message(
            event.reply_token,
            ImageSendMessage('全部資料已清空')
        )

    else:
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage("請輸入「預算」+「數字」" + '\n' + 'ex: 預算30000' + '\n' '輸入「清空」可重置')
        )

@handler.add(MessageEvent, message=AudioMessage)
def handle_content_message(event):
    user_id = event.source.user_id
    print("user_id =", user_id)

    message_id = event.message.id
    message_content = line_bot_api.get_message_content(message_id)
    path = 'static/{}.aac'.format(event.message.id)
    with open(path, 'wb') as fd:
        for chunk in message_content.iter_content():
            fd.write(chunk)

    # Check & Convert Audio Message to Azure
    # BotResponses  =  AzurelBotAudioHandler.LineBotAudioConvert2AzureAudio(path) # this is old one
    BotResponses = AzurelBotAudioHandler.LineBotAudioDirect2Wav(path) # this is new one
    print(BotResponses)

    # read jieba dict for classify
    # jieba.load_userdict('./jieba_dict.txt')
    with open('./jieba_dict_food.txt', 'r', encoding="utf-8") as f:
        food_class = f.read(-1)

    rawData = BotResponses
    tmp_dict = dict()

    # get foodCost_sum & otherCost_sum
    string = "".join(re.findall('\w', rawData)).replace('元', "")
    word = [i for i in re.split('\d', string) if i != ""]
    num = [i for i in re.split('\D', string) if i != ""]
    print(string, word, num)
    print(len(word), len(num))
    # 辨識結果符合格式才執行
    if (len(word) != 0) and (len(num) != 0):
        conn = pymysql.connect(**loginInfo)
        cursor = conn.cursor()
        for i in range(0, len(word)):
            try:
                tmp_dict[word[i]] = num[i]
            except IndexError:
                tmp_dict[word[i]] = 0
            foodCost_sum = sum([int(tmp_dict[food]) for food in tmp_dict.keys() if food in food_class])
            otherCost_sum = sum([int(tmp_dict[food]) for food in tmp_dict.keys() if food not in food_class])

        search_mysql = 'select * from userdata;'
        cursor.execute(search_mysql)
        search_result = cursor.fetchall()

        INDEXNO = search_result[-1][0] + 1  # INDEXNO is PK, +1 keep it unique
        CUSTOMERNO = search_result[-1][1]
        CNAME = search_result[-1][2]
        MAXLIMIT = search_result[-1][3]

        if foodCost_sum == 0:
            print('foodCost_sum')
            print(INDEXNO, CUSTOMERNO, CNAME, MAXLIMIT, foodCost_sum, datetime)
            sql1 = """INSERT INTO userdata (INDEXNO, CUSTOMERNO, CNAME, MAXLIMIT, COST, DATATIME,CATEGORY)
              VALUES ('{a}', '{b}', '{c}', '{d}', '{e}', '{f}', '{g}');
            """.format(a=INDEXNO, b=CUSTOMERNO, c=CNAME, d=MAXLIMIT, e=otherCost_sum, f=datetime, g='其他')

            cursor.execute(sql1)
            conn.commit()
            cursor.close()
            conn.close()
        elif otherCost_sum == 0:
            print('otherCost_sum == 0')
            print(INDEXNO, CUSTOMERNO, CNAME, MAXLIMIT, foodCost_sum, datetime)
            sql2 = """INSERT INTO userdata (INDEXNO, CUSTOMERNO, CNAME, MAXLIMIT, COST, DATATIME,CATEGORY)
              VALUES ('{a}', '{b}', '{c}', '{d}', '{e}', '{f}', '{g}');
            """.format(a=INDEXNO, b=CUSTOMERNO, c=CNAME, d=MAXLIMIT, e=foodCost_sum, f=datetime, g='飲食')

            cursor.execute(sql2)
            conn.commit()
            cursor.close()
            conn.close()
        else:
            print('otherCost_sum & foodCost_sum')
            print(INDEXNO, CUSTOMERNO, CNAME, MAXLIMIT, foodCost_sum, otherCost_sum, datetime)
            sql3 = """INSERT INTO userdata (INDEXNO, CUSTOMERNO, CNAME, MAXLIMIT, COST, DATATIME,CATEGORY)
              VALUES ('{a}', '{b}', '{c}', '{d}', '{e}', '{f}', '{g}');
            """.format(a=INDEXNO, b=CUSTOMERNO, c=CNAME, d=MAXLIMIT, e=otherCost_sum, f=datetime, g='其他')
            sql4 = """INSERT INTO userdata (INDEXNO, CUSTOMERNO, CNAME, MAXLIMIT, COST, DATATIME,CATEGORY)
              VALUES ('{a}', '{b}', '{c}', '{d}', '{e}', '{f}', '{g}');
            """.format(a=INDEXNO + 1, b=CUSTOMERNO, c=CNAME, d=MAXLIMIT, e=foodCost_sum, f=datetime, g='飲食')

            cursor.execute(sql3)
            cursor.execute(sql4)
            conn.commit()
            cursor.close()
            conn.close()

        #
        conn = pymysql.connect(**loginInfo)
        cursor = conn.cursor()
        sql5 = 'select cost, maxlimit, CATEGORY from userdata;'
        cursor.execute(sql5)
        data = cursor.fetchall()
        cursor.close()
        conn.close()

        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(c.cost(data))
        )

if __name__ == "__main__":
    app.run(debug=True)
