import requests
import hmac
import hashlib
import base64
import copy
import xml.etree.ElementTree as ET
import time
import logging
import sys
import concurrent.futures
import configparser

logFormatter = logging.Formatter(
    "%(asctime)s [%(threadName)-12.12s] [%(levelname)-5.5s]  %(message)s")

log = logging.getLogger("test")
log.setLevel(logging.INFO)
fileHandler = logging.FileHandler("log.txt")
fileHandler.setFormatter(logFormatter)
fileHandler.setLevel(logging.INFO)
log.addHandler(fileHandler)

consoleHandler = logging.StreamHandler()
consoleHandler.setFormatter(logFormatter)
consoleHandler.setLevel(logging.INFO)
log.addHandler(consoleHandler)


STATE_RUNNING = "running"
STATE_PENDING = "pending"
STATE_STOPPED = "stopped"

PARAM = {"Actions": "DescribeInstances",
         "SignatureMethod": "HmacSHA1",
         "SignatureVersion": "2",
         "Version": "1.0"
         }

KEY_ACTION = "Action"
KEY_ACCESS_KEY_ID = "AccessKeyId"
KEY_INST_ID_1 = "InstanceId.1"
KEY_SIGNATURE = "Signature"


class Config:
    __instance = None

    @staticmethod 
    def getInstance():
       if Config.__instance == None:
          Config()
       return Config.__instance

    def __init__(self):
         Config.__instance = self
         self.inifile = configparser.ConfigParser()
         self.inifile.read('config.txt')

    def getMaxThreadNum(self):
        return self.inifile.getint('common', 'thread_num')

    def getAccessKeyId(self):
        return self.inifile.get('account', 'access_key_id')

    def getAccessKey(self):
        return self.inifile.get('account', 'access_key')


def mk_signature(param):
    qstring = ""
    for key, val in sorted(param.items()):
        qstring += "{}={}&".format(key, val)

    qstring = qstring[:-1]

    config = Config.getInstance()

    string2sign = "GET\napi.cloudhosting.biglobe.ne.jp\n/api/\n{}".format(
        qstring)
    return base64.b64encode(hmac.new(bytes(config.getAccessKey(), 'utf-8'), bytes(
        string2sign, 'utf-8'), hashlib.sha1).digest()).decode()


def getAllInstIds():
    return getInstId(None, None, False)


def getInstId(instId, state, needPrint):
    param = copy.deepcopy(PARAM)
    param[KEY_ACTION] = "DescribeInstances"

    if instId is not None:
        param[KEY_INST_ID_1] = instId

    param[KEY_SIGNATURE] = mk_signature(param)

    ret = requests.get(
        "https://api.cloudhosting.biglobe.ne.jp/api/", params=param)

    root = ET.fromstring(ret.text)
    errCode = root.find('./Errors/Error/Code')

    if errCode is not None:
        return retErrInfo(errCode, instId)

    if 0:
        assert isinstance(root, ET.Element)

    instIdList = []
    for item in root[1][0][3]:
        instId = item[0].text
        instState = item[2][1].text

        if needPrint:
            log.info("instanceId={} status={}".format(instId, instState))

        if state is None or instState == state:
            instIdList.append(instId)

    return instIdList


def retErrInfo(errCode, instId):
    if errCode.text == "InvalidInstanceID.NotFound":
        if instId is None:
            log.warn("インスタンスが存在しません。")
        else:
            log.warn("インスタンスID={}が存在しません。".format(instId))
    else:
        if instId is None:
            log.error("インスタンスの情報取得でエラーが発生しました。")
        else:
            log.error("インスタンスID={}の情報取得でエラーが発生しました。".format(instId))

    return []


def startInst(instId):
    callApi(instId, "StartInstances", "起動")


def terminateInst(instId):
    try:
        instIdList = getInstId(instId, STATE_RUNNING, True)
        if len(instIdList) > 0:
            callApi(instId, "StopInstances", "停止")

        checkInstStopped(instId)
        return callApi(instId, "TerminateInstances", "削除")
    except Exception as e:
        log.exception("インスタンスID={}の処理中にエラー発生!! %s".format(instId), e)
        return 0


def checkInstStopped(instId):
    log.info("インスタンスID={}の停止チェックを行います。".format(instId))
    while True:
        activeInstList = getInstId(instId, STATE_RUNNING, False)
        if len(activeInstList) == 0:
            break
        log.info("instanceId={} status={}".format(instId, STATE_RUNNING))
        time.sleep(10)

    while True:
        activeInstList = getInstId(instId, STATE_PENDING, False)
        if len(activeInstList) == 0:
            break
        log.info("instanceId={} status={}".format(instId, STATE_PENDING))
        time.sleep(10)


def callApi(instId, action, actionJapanese):
    param = copy.deepcopy(PARAM)
    param[KEY_ACTION] = action
    param[KEY_INST_ID_1] = instId
    param[KEY_SIGNATURE] = mk_signature(param)

    ret = requests.get(
        "https://api.cloudhosting.biglobe.ne.jp/api/", params=param)

    if ret.status_code == 200:
        log.info("InstanceId={}の{}要求実行完了".format(instId, actionJapanese))
        return 1
    else:
        log.error("InstanceId={}の{}要求に失敗しました。後程再実行してください。".format(
            instId, actionJapanese))
        return 0


def readInstList(inst_list_file):
    instList = []
    for line in open(inst_list_file, "r"):
        line = line.replace("\n", "")
        line = line.replace("\r", "")
        if line != "":
            instList.append(line)

    return instList


def confirmExecute(instIdList):
    for instId in instIdList:
        log.info("instanceId={}".format(instId))
    log.info("上記インスタンスの削除を行います。続行する場合はエンターを押してください。停止する場合はCtrl+Cを押してください")
    input()


def dispSuccessCnt(allCnt, ret):
    successCnt = 0
    [successCnt + i for i in ret]
    log.info("インスタンス数={} 削除成功数={}".format(allCnt, successCnt))


def main():
    try:
        config = Config.getInstance()
        PARAM[KEY_ACCESS_KEY_ID] = config.getAccessKeyId()

        log.info("停止対象インスタンス情報の取得・・・")
        if len(sys.argv) == 2:
            instIdList = readInstList(sys.argv[1])
        else:
            instIdList = getAllInstIds()

        if len(instIdList) == 0:
            log.warning("停止可能なインスタンスが存在しません")
            return

        confirmExecute(instIdList)

        with concurrent.futures.ThreadPoolExecutor(max_workers=config.getMaxThreadNum()) as executor:
            ret = executor.map(terminateInst, instIdList)

        dispSuccessCnt(len(instIdList), ret)

    except Exception as e:
        log.exception("エラー発生!! %s", e)

    finally:
        log.info("処理を終了します。エンターキーを押してください。")
        input()


if __name__ == '__main__':
    main()
