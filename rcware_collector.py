import csv
import time
from datetime import datetime, timedelta

import zeep

from credentials import username, password

# logging.basicConfig(level=logging.DEBUG)

RCW_VARIABLE_COUNT = 3000
WSDL = 'wsdl/RcWareDbAccess.wsdl'

settings = zeep.Settings(strict=True, xml_huge_tree=True, force_https=False, raw_response=False)

# Available ports are HistoryAccess, HistoryAccessGZip, HistoryAccess1. Only HistoryAccess seems to be alive.
client = zeep.Client(wsdl=WSDL, settings=settings, port_name='HistoryAccess')

factory = client.type_factory('http://schemas.datacontract.org/2004/07/ESG.Db.Server.Shared')

creds = factory.Credentials(Name=username, Password=password)


def load_mapping(filename):
    measurements_map = {}
    influx_keys = ('plant', 'device_type', 'device', 'measurement', 'via')

    with open(filename, 'r') as f:
        for r in csv.DictReader(f):
            measurements_map[(r['RC_PROJECT_NAME'], r['RC_GUID'])] = {k: r[k] for k in influx_keys}
    print("Loaded", len(measurements_map), "measurements")
    return measurements_map


def rcw_to_influx(mvr, rcw_mapping):
    # (StationName: DPGuid) tuple used as key in the config dictionary
    lookup = (mvr['Keys']['KeyValuePair'][5]['Value'], mvr['Keys']['KeyValuePair'][1]['Value'])

    datapoints = []

    # lookup = tuple([k['Value'] for k in mvr['Keys']['KeyValuePair'] if k['Key'] in ['DPGuid', 'StationName']])  # todo this can be indices
    for value in mvr['Vals']['I']:
        ts = value['Gt']
        value = value['Dv']

        dp_dict = rcw_mapping[lookup]

        data_point = {
            "measurement": dp_dict['measurement'],
            "tags": {tag: dp_dict[tag] for tag in ["device", "plant", "device_type"]},
            "time": ts,
            "fields": {
                "value": float(value)
            }
        }
        datapoints.append(data_point)
    return datapoints


def read_rcware_measurements(rcw_mapping: dict, since: datetime, to=datetime.utcnow()):
    """

    :param to: UTC datetime to read data to. Default: utcnow()
    :param rcw_mapping: metrics mapping between rcware and influx
    :param since: UTC datetime to read data from
    :return: List of dictionaries ready for insertion in influxdb
    """
    data = []
    now = datetime.utcnow()

    for rcw_meas in rcw_mapping:
        # Make key value pairs for GetData
        plant = factory.KeyValuePair(Key='StationName', Value=rcw_meas[0])
        uuid = factory.KeyValuePair(Key='DPGuid', Value=rcw_meas[1])
        aakvp = factory.ArrayOfArrayOfKeyValuePair(factory.ArrayOfKeyValuePair([plant, uuid]))

        val_offset = 0
        while True:
            res = client.service.GetData(
                credentials=creds,
                variablesKey=aakvp,
                utcFrom=since,
                utcTo=now,
                variableOffset=0,
                variableCount=1,
                valueOffset=val_offset,
                valueCount=RCW_VARIABLE_COUNT,
            )

            if res['returnCode'] != "0;OK;":
                print(res['returnCode'], plant, uuid)
                break

            for mvr in res['GetDataResult']['Mvr']:
                data.append(rcw_to_influx(mvr, rcw_mapping))

            val_offset = res['nextValueOffset']
            if val_offset == -1:  # no more values to read
                break
    return data


if __name__ == '__main__':
    config = load_mapping('rcware_collector-config.csv')

    print('Alive:', client.service.ServerAlive())
    print('Check Creds:', client.service.CheckCredentials(creds))

    while True:
        start = time.time()
        data = read_rcware_measurements(config, datetime.utcnow() - timedelta(minutes=5))
        print(len(data), "dps done in", time.time() - start)
        # print(data)

        time.sleep(300)
