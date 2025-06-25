"""
将B站BV号转换为av号
或将av号转换为BV号
叫bv2av是因为一开始没打算做第二个功能
shniubobo
"""
from json.decoder import JSONDecodeError
import requests

BV2AV_API = 'https://api.bilibili.com/x/web-interface/view'  # ?bvid=
AV2BV_API = 'https://api.bilibili.com/x/web-interface/archive/stat'  # ?aid=
HEADER = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) \
Chrome/80.0.3987.149 Safari/537.36'}


def bv_to_av(bv):
    r = requests.get(BV2AV_API, {'bvid': bv}, headers=HEADER)
    response = decode_json(r)
    try:
        return str(response['data']['aid'])
    except (KeyError, TypeError):
        return '获取av号失败'


def av_to_bv(av):
    # 带'av'的话识别不了，得先去掉
    if 'av'.lower() in av.lower():
        av = av.lower().strip('av')

    r = requests.get(AV2BV_API, {'aid': av}, headers=HEADER)
    response = decode_json(r)
    try:
        return response['data']['bvid']
    except (KeyError, TypeError):
        return '获取BV号失败'


def decode_json(r):
    try:
        response = r.json()
    except JSONDecodeError:
        # 虽然用的是requests的json方法，但要捕获的这个异常来自json模块
        return -1
    else:
        return response


def main():
    while True:
        try:
            mode = int(input('1.BV -> av\n2.av -> BV\n请输入对应编号:'))
            if mode == 1:
                bv = input('请输入BV号:')
            elif mode == 2:
                av = input('请输入av号:')
            else:
                raise ValueError
        except ValueError:
            print('输入错误！')
        else:
            break

    if mode == 1:
        print('对应av号:av' + bv_to_av(bv))
    elif mode == 2:
        print('对应BV号:' + av_to_bv(av))
    input('按回车键退出')


if __name__ == '__main__':
    main()