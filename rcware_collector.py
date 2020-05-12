import csv
import time
from datetime import datetime, timedelta

import zeep
from influxdb import InfluxDBClient

from credentials import username, password

# logging.basicConfig(level=logging.DEBUG)

RCW_GETDATA_VALUE_COUNT = 3000
WSDL = 'wsdl/RcWareDbAccess.wsdl'

settings = zeep.Settings(strict=True, xml_huge_tree=True, force_https=False, raw_response=False)

# Available ports are HistoryAccess, HistoryAccessGZip, HistoryAccess1. Only HistoryAccess seems to be alive.
client = zeep.Client(wsdl=WSDL, settings=settings, port_name='HistoryAccess')

factory = client.type_factory('http://schemas.datacontract.org/2004/07/ESG.Db.Server.Shared')

creds = factory.Credentials(Name=username, Password=password)

influxdb = InfluxDBClient('influxdb.power-hash.com', port=80)


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
    # lookup = tuple([k['Value'] for k in mvr['Keys']['KeyValuePair'] if k['Key'] in ['DPGuid', 'StationName']])  # todo this can be indices

    datapoints = []

    for value in mvr['Vals']['I']:
        ts = value['Gt']
        val = value['Dv']

        dp_dict = rcw_mapping[lookup]

        dp = {
            "measurement": dp_dict['measurement'],
            "tags": {tag: dp_dict[tag] for tag in ["device", "plant", "device_type"]},
            "time": ts,
            "fields": {
                "value": float(val)
            }
        }
        datapoints.append(dp)
    return datapoints


def read_rcware_measurements(rcw_mapping: dict, since: datetime, to=datetime.utcnow()):
    """

    :param rcw_mapping: metrics mapping between rcware and influx
    :param since: UTC datetime to read data from
    :param to: UTC datetime to read data to. Default: utcnow()
    :return: List of dictionaries ready for insertion in influxdb
    """
    data = []

    for rcw_msrmt in rcw_mapping:
        # Make key value pairs for GetData
        plant = factory.KeyValuePair(Key='StationName', Value=rcw_msrmt[0])
        uuid = factory.KeyValuePair(Key='DPGuid', Value=rcw_msrmt[1])
        aakvp = factory.ArrayOfArrayOfKeyValuePair(factory.ArrayOfKeyValuePair([plant, uuid]))

        val_offset = 0
        while True:
            res = client.service.GetData(
                credentials=creds,
                variablesKey=aakvp,
                utcFrom=since,
                utcTo=to,
                variableOffset=0,
                variableCount=1,
                valueOffset=val_offset,
                valueCount=RCW_GETDATA_VALUE_COUNT,
            )

            if res['returnCode'] != "0;OK;":
                print(res['returnCode'], plant, uuid)
                break

            try:
                for mvr in res['GetDataResult']['Mvr']:
                    for dp in rcw_to_influx(mvr, rcw_mapping):
                        data.append(dp)
            except Exception:
                print(res, rcw_msrmt)
                raise

            val_offset = res['nextValueOffset']
            if val_offset == -1:  # no more values to read for current variable
                break
    return data


if __name__ == '__main__':
    config = load_mapping('rcware_collector-config.csv')

    print('Alive:', client.service.ServerAlive())
    print('Check Creds:', client.service.CheckCredentials(creds))

    while True:
        start = time.time()
        data = read_rcware_measurements(config, datetime.utcnow() - timedelta(minutes=5))
        print(int(start), len(data), "dps done in", f'{time.time() - start:.2f}')
        # print(data)

        influxdb.create_database('rcware_test')
        influxdb.switch_database('rcware_test')
        influxdb.write_points(data)

        time.sleep(300-(time.time()-start))
