"""Slack bot on AWS Lambda."""
import asyncio
import datetime
import json
import logging
import os
import random
import traceback
import xml.etree.ElementTree as ET

import requests
from bs4 import BeautifulSoup

LOGGER = logging.getLogger()
LOGGER.setLevel(logging.DEBUG)

stream_handler = logging.StreamHandler()
stream_handler.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s [%(filename)s in %(lineno)d]')
stream_handler.setFormatter(formatter)
LOGGER.addHandler(stream_handler)

# 日本時間に調整
NOW = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=9)

# requests のユーザーエージェントを書き換えたい
HEADER = {
    'User-agent': '''\
Mozilla/5.0 (Windows NT 10.0; Win64; x64) \
AppleWebKit/537.36 (KHTML, like Gecko) Chrome/79.0.3945.88 Safari/537.36'''
}

USERNAME = os.environ.get('username', 'slackbot')
HOTPEPPER = os.environ['hotpepper']
JALAN = os.environ['jalan']


def delete_old_publications():
    try:
        results = requests.get(
            "https://slack.com/api/search.messages",
            params={
                'token': os.environ['token2'],
                'query': os.environ['query'],
                'sort': 'timestamp',
                'sort_dir': 'asc',
            }
        )
        if results.status_code != 200:
            LOGGER.error(f"status code: {results.staus_code}, reason: {results.reason}, content: {results.content}")
        message_list = results.json()['messages']['matches']

        for msg in message_list:
            # 14日以上過ぎていたら削除する
            target = datetime.datetime.fromtimestamp(float(msg['ts']))
            limit = datetime.datetime.now() - datetime.timedelta(days=14)
            if target < limit:
                print(msg['username'], msg['ts'], msg['text'])
                delete_msg = requests.post(
                    'https://slack.com/api/chat.delete',
                    headers={
                        'content-type': 'application/json; charset=utf-8',
                        "Authorization": f"Bearer {os.environ['oauth_token']}",
                    },
                    data=json.dumps({
                        'token': os.environ['api_token'],
                        'channel': msg['channel']['id'],
                        'ts': msg['ts']
                    })
                )
                LOGGER.info(f"{delete_msg.status_code} {delete_msg.json()}")
    except Exception:
        LOGGER.error(traceback.format_exc())


class MethodGroup:
    """やりたい処理を定義."""

    @staticmethod
    def _send_data(message: str, channel=None, challenge=None, slacktype=None) -> None:
        """Slack へ送信.

        :param str message: 改行コードはLFでお願いします
        :param dict param:
        """
        headers = {
            'Content-Type': 'application/json; charset=UTF-8',
            "Authorization": f"Bearer {os.environ['oauth_token']}",
        }
        url = "https://slack.com/api/chat.postMessage"
        payload = {
            'text': message,
            "token": os.environ['api_token'],
            "channel": channel if channel else os.environ['slack_channnel'],
            "username": USERNAME,
        }
        if challenge:
            payload['challenge'] = challenge
        if slacktype:
            payload['type'] = slacktype

        LOGGER.info(f"[SEND SLACK] {url} [DATA]{payload} [HEADER] {headers}")
        res = requests.post(
            url, data=json.dumps(payload).encode("utf-8"), headers=headers)
        LOGGER.info(f"[RESPONSE] [STATUS]{res.status_code} [HEADER]{res.headers} [CONTENT]{res.content}")

    @staticmethod
    def _send_image(channel=None) -> None:
        """Slack へ画像を送信（テスト）."""
        url = "https://slack.com/api/files.upload"
        files = {'file': open('erabee.png', 'rb')}
        payload = {
            "token": os.environ['oauth_token'],
            "channels": channel if channel else os.environ['slack_channnel'],
            "filename": "erabee.png",
        }
        LOGGER.info(f"[REQUEST] [URL]{url} [PARAM]{payload}")
        res = requests.post(url, params=payload, files=files)
        LOGGER.info(f"[RESPONSE] [STATUS]{res.status_code} [HEADER]{res.headers} [CONTENT]{res.content}")

    @staticmethod
    async def help(param: dict, *args) -> None:
        """メソッド一覧."""
        methods = [a for a in dir(MethodGroup) if '_' not in a]
        if len(args) > 0 and getattr(MethodGroup, args[0], None):
            message = getattr(MethodGroup, args[0]).__doc__.replace('    ', '')
        else:
            message = 'メソッド一覧 '
            message += ', '.join(methods)
        MethodGroup._send_data(message, **param)

    @staticmethod
    async def lunch(param: dict, *args) -> None:
        """ランチ営業しているところを検索します.

        引数なし、もしくは一つの場合はデフォルト座標の近くでキーワード検索します。
        引数を2つ以上指定した場合、それらでキーワード検索します。
        この時のキーワードには場所も含まれます。
        """
        _param = {
            'key': HOTPEPPER,
            'large_service_area': 'SS10',  # 関東
            'range': '3',
            'order': '2',
            'type': 'lite',
            'format': 'json',
            'count': '100',
            'lunch': '1',
        }
        if not args or len(args) == 1:
            _param['lat'] = os.environ['default_lat']
            _param['lng'] = os.environ['default_lng']
        if len(args) > 0:
            _param['keyword'] = ' '.join(list(args))
        hotpepper = requests.get(
            'http://webservice.recruit.co.jp/hotpepper/gourmet/v1/',
            params=_param,
            headers=HEADER)
        shops = hotpepper.json()['results']['shop']
        if len(shops) > 0:
            shop = random.choice(shops)
            message = f'<{shop["urls"]["pc"]}|{shop["name"]}>'
        else:
            message = '検索結果がありません'
        message += '　　Powered by <https://webservice.recruit.co.jp/|ホットペッパー Webサービス>'
        MethodGroup._send_data(message, **param)

    @staticmethod
    async def qiita(param: dict, *args) -> None:
        """Qiita の新着を3つ教えてくれます."""
        res = requests.get('https://qiita.com/api/v2/items?page=1&per_page=3',
                           headers=HEADER)
        data = res.json()
        msg = []
        for d in data:
            msg.append(f"<{d['url']}|{d['title']}>")
        message = '\n'.join(msg)
        MethodGroup._send_data(message, **param)

    @staticmethod
    async def nomitai(param: dict, *args) -> None:
        """いつどこに飲みに行くのか決めてくれます.

        引数なし、もしくは一つの場合は溜池山王辺りを中心にしてキーワード検索します。
        引数を2つ以上指定した場合、それらでキーワード検索します。
        キーワードには場所も含まれます。
        """
        _param = {
            'key': HOTPEPPER,
            'large_service_area': 'SS10',  # 関東
            'range': '5',
            'order': '2',
            'type': 'lite',
            'format': 'json',
            'count': '100',
        }
        if not args or len(args) == 1:
            _param['lat'] = os.environ['default_lat']
            _param['lng'] = os.environ['default_lng']
            if not args:
                # デフォルトは居酒屋
                _param['genre'] = 'G001'
        if len(args) > 0:
            _param['keyword'] = ' '.join(list(args))
        if len(args) >= 2:
            # 範囲を絞る
            _param['range'] = 3

        hotpepper = requests.get(
            'http://webservice.recruit.co.jp/hotpepper/gourmet/v1/',
            params=_param,
            headers=HEADER)
        shops = hotpepper.json()['results']['shop']
        if len(shops) == 0:
            message = '検索結果がありません'
        else:
            shop = random.choice(shops)
            message = f"<{shop['urls']['pc']}|{shop['name']}>"
        message += '　　Powered by <https://webservice.recruit.co.jp/|ホットペッパー Webサービス>'
        MethodGroup._send_data(message, **param)

    @staticmethod
    async def kissa(param: dict, *args) -> None:
        """喫茶店を検索します.

        引数なしの場合はデフォルト座標の近くでキーワード検索します。
        引数を指定した場合、それらでキーワード検索します。
        キーワードには場所も含まれます。
        """
        _param = {
            'key': HOTPEPPER,
            'large_service_area': 'SS10',  # 関東
            'range': '2',
            'order': '2',
            'type': 'lite',
            'format': 'json',
            'count': '100',
            'genre': 'G014'
        }
        if not args or len(args) == 0:
            _param['lat'] = os.environ['default_lat']
            _param['lng'] = os.environ['default_lng']
        if len(args) > 0:
            _param['keyword'] = ' '.join(list(args))

        hotpepper = requests.get(
            'http://webservice.recruit.co.jp/hotpepper/gourmet/v1/',
            params=_param,
            headers=HEADER)
        shops = hotpepper.json()['results']['shop']
        if len(shops) == 0:
            message = '検索結果がありません'
        else:
            shop = random.choice(shops)
            message = f"<{shop['urls']['pc']}|{shop['name']}>"
        message += '　　Powered by <https://webservice.recruit.co.jp/|ホットペッパー Webサービス>'
        MethodGroup._send_data(message, **param)

    @staticmethod
    async def yasumitai(param: dict, *args) -> None:
        """たまには旅行もいいね.

        引数として、都道府県名を受け付けます。
        """
        # 1 から 47 のランダムな整数
        test = random.randrange(1, 48)
        pref = format(test * 10000, '06d')
        # あるいは都道府県指定（順番とコードが対応していますよ）
        pref_list = [
            '北海道', '青森県', '岩手県', '宮城県', '秋田県', '山形県',
            '福島県', '栃木県', '群馬県', '茨城県', '埼玉県', '千葉県',
            '東京都', '神奈川県', '山梨県', '長野県', '新潟県', '富山県',
            '石川県', '福井県', '静岡県', '岐阜県', '愛知県', '三重県',
            '滋賀県', '京都府', '大阪府', '兵庫県', '奈良県', '和歌山県',
            '鳥取県', '島根県', '岡山県', '広島県', '山口県', '徳島県',
            '香川県', '愛媛県', '高知県', '福岡県', '佐賀県', '長崎県',
            '熊本県', '大分県', '宮崎県', '鹿児島県', '沖縄県',
        ]
        if args and len(args) > 0:
            for i, pr in enumerate(pref_list, start=1):
                if args[0] and args[0] in pr:
                    pref = format(i * 10000, '06d')
                    break
        _param = {
            'key': JALAN,
            'pref': pref,
        }
        jalan = requests.get(
            'http://jws.jalan.net/APIAdvance/HotelSearch/V1/',
            params=_param,
            headers=HEADER)
        root = ET.fromstring(jalan.text)
        hotels = []
        for child in root:
            if 'hotel' in child.tag.lower():
                hotels.append({
                    'name': child[1].text,
                    'url': child[6].text
                })
        if len(hotels) == 0:
            message = '検索結果がありません'
        else:
            hotel = random.choice(hotels)
            message = f"<{hotel['url']}|{hotel['name']}>"
        message += '　　<https://www.jalan.net/jw/jwp0000/jww0001.do/|じゃらん Web サービス>'
        MethodGroup._send_data(message, **param)

    @staticmethod
    async def itsEvents(param: dict, *args) -> None:
        """関東ITソフトウェア健康保険組合のイベント情報を返します."""
        ret = requests.get('https://www.its-kenpo.or.jp/NEWS/event_rss.xml',
                           headers=HEADER)
        root = ET.fromstring(ret.content.decode('utf8'))
        msg = []
        for child in root[0]:
            if 'item' in child.tag.lower():
                msg.append(f'<{child[1].text}|{child[0].text}>')
        message = '関東ITソフトウェア健康保険組合のイベント情報です\n'
        message += '\n'.join(msg)
        MethodGroup._send_data(message, **param)

    @staticmethod
    async def yahoo(param: dict, *args) -> None:
        """ヤフーニュースを取得します."""
        ret = requests.get('https://news.yahoo.co.jp', headers=HEADER)
        # utf8 以外だったら以下みたいにデコードする
        # html = ret.content.decode('sjis')
        yahoo = BeautifulSoup(ret.text, 'html.parser')
        topics = yahoo.select('ul.topicsList_main')[0].select('li>a')
        message = '主要なニュースをお伝えします\n'
        msg = []
        for topic in topics:
            msg.append(f"<{topic.get('href')}|{topic.text}>")
        message += '\n'.join(msg)
        MethodGroup._send_data(message, **param)

    @staticmethod
    async def itmediaRanking(*args) -> None:
        """ITmediaからランキングを取得します."""
        LOGGER.info('--START-- itmediaRanking')
        url = 'https://www.itmedia.co.jp/news/subtop/ranking/'
        LOGGER.debug(f"GET {url} header: {HEADER}")
        ret = requests.get(url, headers=HEADER)
        site = BeautifulSoup(ret.content.decode('sjis'), 'html.parser')
        root = site.select('div#Ranking')[0].select('div.colBoxIndexRight')
        message = '【 ITmedia NEWSの本日のランキング10件 】\n'
        msg = []
        for item in root:
            msg.append(
                f"<{item.select('a')[0].get('href')}|{item.select('a')[0].text}>")
            if len(msg) >= 10:
                break
        message += '\n'.join(msg)
        MethodGroup._send_data(message)
        LOGGER.info('--END-- itmediaRanking')

    @staticmethod
    async def itmediaYesterday(*args) -> None:
        """ITmediaの昨日のニュースをお伝えします."""
        LOGGER.info('--START-- itmediaYesterday')
        yesterday = NOW - datetime.timedelta(days=1)
        s_yd = f'{yesterday.year}年{yesterday.month}月{yesterday.day}日'
        url = f"https://www.itmedia.co.jp/news/subtop/archive/{yesterday.strftime('%Y%m')[2:]}.html"
        LOGGER.debug(f"yesterday is {yesterday}")
        LOGGER.debug(f"GET {url} header: {HEADER}")
        ret = requests.get(url, headers=HEADER)
        site = BeautifulSoup(ret.content.decode('sjis'), 'html.parser')
        root = site.select('div.colBoxBacknumber')[
            0].select('div.colBoxInner>div')
        message = '【 ITmediaの昨日のニュース一覧 】\n'
        msg = []
        for i, item in enumerate(root):
            if 'colBoxSubhead' in item.get('class', []) and item.text == s_yd:
                for a in root[i + 1].select('ul>li'):
                    msg.append(
                        f"<https:{a.select('a')[0].get('href')}|{a.select('a')[0].text}>")
                break
        if len(msg) > 0:
            message += '\n'.join(msg)
        else:
            message = 'ITmediaの昨日のニュースはありませんでした。'
        MethodGroup._send_data(message)
        LOGGER.info('--END-- itmediaYesterday')

    @staticmethod
    async def zdJapan(*args) -> None:
        """ZDNet Japanの昨日のニュースを取得."""
        LOGGER.info('--START-- zdJapan')
        yesterday = NOW - datetime.timedelta(days=1)
        s_yd = yesterday.strftime('%Y-%m-%d')
        base = 'https://japan.zdnet.com'
        url = base + '/archives/'
        LOGGER.debug(f"yesterday is {yesterday}")
        LOGGER.debug(f"GET {url} header: {HEADER}")
        ret = requests.get(url, headers=HEADER)
        site = BeautifulSoup(ret.content.decode('utf8'), 'html.parser')
        root = site.select('div.pg-mod')
        message = '【 ZDNet Japanの昨日のニュース一覧 】\n'
        msg = []
        for div in root:
            span = div.select('h2.ttl-line-center>span')
            if span and span[0].text == '最新記事一覧':
                for li in div.select('ul>li'):
                    if s_yd in li.select('p.txt-update')[0].text:
                        anchor = li.select('a')[0]
                        msg.append(
                            f"<{base + anchor.get('href')}|{anchor.text}>")
                break
        if len(msg) > 0:
            message += '\n'.join(msg)
        else:
            message = 'ZDNet Japanの昨日のニュースはありませんでした。'
        MethodGroup._send_data(message)
        LOGGER.info('--END-- zdJapan')

    @staticmethod
    async def weeklyReport(*args) -> None:
        """JPCERT から Weekly Report を取得."""
        LOGGER.info('--START-- weeklyReport')
        url = 'https://www.jpcert.or.jp'
        today = NOW.strftime('%Y-%m-%d')
        LOGGER.debug(f"today is {today}")
        LOGGER.debug(f"GET {url} header: {HEADER}")
        ret = requests.get(url, headers=HEADER)
        jpcert = BeautifulSoup(ret.content.decode('utf-8'), 'html.parser')
        whatsdate = jpcert.select('a.fl')[0].text.replace('号', '')
        if today == whatsdate:
            message = f"【 JPCERT の Weekly Report {jpcert.select('a.fl')[0].text} 】\n"
            message += url + jpcert.select('a.fl')[0].get('href') + '\n'
            wkrp = jpcert.select('div.contents')[0].select('li')
            for i, item in enumerate(wkrp, start=1):
                message += f"{i}. {item.text}\n"
            MethodGroup._send_data(message)
        LOGGER.info('--END-- weeklyReport')

    @staticmethod
    async def noticeAlert(*args) -> None:
        """当日発表の注意喚起もしくは脆弱性関連情報を取得."""
        LOGGER.info('--START-- noticeAlert')
        url = 'https://www.jpcert.or.jp'
        today = NOW.strftime('%Y-%m-%d')
        LOGGER.debug(f"today is {today}")
        yesterday = NOW - datetime.timedelta(days=1)
        # 12:00 に実行するので、前日の 11:59 以降をデータ取得対象にする
        yesterday = datetime.datetime(
            yesterday.year,
            yesterday.month,
            yesterday.day,
            11, 59, 59
        )
        LOGGER.debug(f"yesterday is {yesterday}")
        LOGGER.debug(f"GET {url} header: {HEADER}")
        ret = requests.get(url, headers=HEADER)
        jpcert = BeautifulSoup(ret.content.decode('utf-8'), 'html.parser')
        items = jpcert.select('div.container')
        notice = '【 JPCERT の直近の注意喚起 】\n'
        warning = '【 JPCERT の直近の脆弱性関連情報 】\n'
        notice_list = []
        warning_list = []
        for data in items:
            if data.select('h3') and data.select('h3')[0].text == '注意喚起':
                for li in data.select('ul.list>li'):
                    published = li.select('a')[0].select(
                        'span.left_area')[0].text
                    title = li.select('a')[0].select('span.right_area')[0].text
                    LOGGER.debug(f"{published} {title}")
                    if today in published:
                        link = url + li.select('a')[0].get('href')
                        notice_list.append(f"{today} {title} {link}")
                    if yesterday.strftime('%Y-%m-%d') in published:
                        link = url + li.select('a')[0].get('href')
                        notice_list.append(
                            f"{yesterday.strftime('%Y-%m-%d')} <{link}|{title}>")
            if data.select('h3') and data.select('h3')[0].text == '脆弱性関連情報':
                for li in data.select('ul.list>li'):
                    published = li.select('a')[0].select(
                        'span.left_area')[0].text.strip()
                    dt_published = datetime.datetime.strptime(
                        published, '%Y-%m-%d %H:%M')
                    title = li.select('a')[0].select('span.right_area')[0].text
                    LOGGER.debug(f"{published} {title}")
                    if yesterday <= dt_published:
                        link = li.select('a')[0].get('href')
                        warning_list.append(f"<{link}|{title}>")
        if len(notice_list) > 0:
            notice += '\n'.join(notice_list)
            MethodGroup._send_data(notice)
        if len(warning_list) > 0:
            warning += '\n'.join(warning_list)
            MethodGroup._send_data(warning)
        LOGGER.info('--END noticeAlert')

    @staticmethod
    async def ait(*args) -> None:
        """アットマークITの本日の総合ランキングを返します."""
        LOGGER.info('--START-- ait')
        url = 'https://www.atmarkit.co.jp/json/ait/rss_rankindex_all_day.json'
        LOGGER.debug(f"GET {url} header: {HEADER}")
        ret = requests.get(url, headers=HEADER)
        json_str = ret.content.decode('sjis').replace(
            'rankingindex(', '').replace(')', '').replace('\'', '"')
        json_data = json.loads(json_str)
        message = '【 アットマークITの本日の総合ランキング10件 】\n'
        msg = []
        for item in json_data['data']:
            if item:
                msg.append(f"<{item['link']}|{item['title'].replace(' ', '')}>")
            if len(msg) >= 10:
                break
        message += '\n'.join(msg)
        MethodGroup._send_data(message)
        LOGGER.info('--END-- ait')


async def runner():
    await MethodGroup.ait()
    await MethodGroup.itmediaRanking()
    await MethodGroup.itmediaYesterday()
    await MethodGroup.zdJapan()
    await MethodGroup.weeklyReport()
    await MethodGroup.noticeAlert()


def simple_api(body):
    """Lambda をシンプルにたたいた場合の処理."""
    ret = requests.get('https://news.yahoo.co.jp', headers=HEADER)
    # utf8 以外だったら以下みたいにデコードする
    # html = ret.content.decode('sjis')
    yahoo = BeautifulSoup(ret.text, 'html.parser')
    topics = yahoo.select('ul.topicsList_main')[0].select('li>a')
    msg = []
    for topic in topics:
        msg.append({
            'title': topic.text,
            'url': topic.get('href'),
        })
    return msg


def lambda_handler(event, context):
    """eventの中身はログ見てね."""
    try:
        LOGGER.info('--LAMBDA START--')
        LOGGER.info(f"event: {json.dumps(event)}")
        LOGGER.info(f"context: {context}")
        LOGGER.debug(f"Japan Time is : {NOW}")

        if isinstance(event, dict) and event.get('source') == 'aws.events':
            # CloudWatch Event のやつ
            asyncio.run(runner())
            delete_old_publications()

        if isinstance(event, dict) and event.get('body'):
            # Slack App のやつ
            LOGGER.debug(f"body: {event.get('body')}")
            _payload = json.loads(event.get('body'))
            text = _payload.get('event', {}).get('text', '').replace('　', ' ')
            args = text.split(' ')
            # 先頭は bot のIDなので捨てる
            _method = args[1]
            _param = args[2:]
            interactive_param = {
                'channel': _payload.get('event', {}).get('channel'),
                'challenge': _payload.get('challenge'),
                'slacktype': _payload.get('type')
            }

            LOGGER.debug(f"_method: {_method} _param: {_param}")
            if event.get('headers', {}).get('X-Slack-Retry-Num'):
                # Slackがリトライするの早すぎなのでヘッダーを見てリトライは殺します
                slack_payload = {
                    "token": os.environ['api_token'],
                    "channel": interactive_param.get('channel', os.environ['slack_channnel']),
                    "challenge": interactive_param['challenge'],
                    "type": interactive_param['slacktype'],
                    "username": USERNAME,
                }
                ret = {
                    'statusCode': '200',
                    'body': json.dumps(slack_payload, ensure_ascii=False),
                    'headers': {
                        'Content-Type': 'application/json; charset=UTF-8',
                        "Authorization": f"Bearer {os.environ['oauth_token']}",
                    },
                }
                LOGGER.info(f'[RETURN] {ret}')
                return ret

            if getattr(MethodGroup, _method, None):
                asyncio.run(getattr(MethodGroup, _method)(interactive_param, *_param))

    except Exception:
        LOGGER.error(traceback.format_exc())

    if isinstance(event.get('body'), str):
        # AWS Lambda でテスト実行するとここが走る
        payload = simple_api(event['body'])
    else:
        payload = {
            'event': event,
            'token': os.environ['api_token'],
        }

    ret = {
        'statusCode': '200',
        'body': json.dumps(payload, ensure_ascii=False),
        'headers': {
            'Content-Type': 'application/json; charset=UTF-8',
            "Authorization": f"Bearer {os.environ['oauth_token']}",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "X-Requested-With, Origin, X-Csrftoken, Content-Type, Accept",
        },
    }
    LOGGER.info(f'[RETURN] {ret}')
    LOGGER.info('--LAMBDA END--')
    return ret
