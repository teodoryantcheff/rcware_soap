import asyncio
import csv
import time
from datetime import datetime, timedelta

import zeep
from influxdb import InfluxDBClient
from zeep.asyncio import AsyncTransport

from credentials import username, password

# logging.basicConfig(level=logging.DEBUG)

RCW_GETDATA_VALUE_COUNT = 3000
WSDL = 'wsdl/RcWareDbAccess.wsdl'

MAX_CONCURRENCY = 2

loop = asyncio.get_event_loop()
loop.set_debug(False)

settings = zeep.Settings(strict=True, xml_huge_tree=True, force_https=False, raw_response=False)
transport = AsyncTransport(loop, cache=None)  # todo remove no cache
# Available ports are HistoryAccess, HistoryAccessGZip, HistoryAccess1. Only HistoryAccess seems to be alive.
client = zeep.Client(wsdl=WSDL, settings=settings, port_name='HistoryAccess', transport=transport)
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


rcw_mapping = load_mapping('rcware_collector-config.csv')


def rcw_to_influx(mvr):
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


async def read_single_measurement(semaphore, rcw_measurement, since: datetime, to):
    async with semaphore:
        # Make key value pairs for GetData
        plant = factory.KeyValuePair(Key='StationName', Value=rcw_measurement[0])
        uuid = factory.KeyValuePair(Key='DPGuid', Value=rcw_measurement[1])
        aakvp = factory.ArrayOfArrayOfKeyValuePair(factory.ArrayOfKeyValuePair([plant, uuid]))

        data = []

        val_offset = 0
        while True:
            res = await client.service.GetData(
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
                    for dp in rcw_to_influx(mvr):
                        data.append(dp)
            except Exception:
                print(res, rcw_measurement)
                raise

            val_offset = res['nextValueOffset']
            if val_offset == -1:  # no more values to read for current variable
                break
        return data


async def read_rcware_measurements(since: datetime, to=datetime.utcnow()):
    """

    :param since: UTC datetime to read data from
    :param to: UTC datetime to read data to. Default: utcnow()
    :return: List of dictionaries ready for insertion in influxdb
    """
    semaphore = asyncio.Semaphore(MAX_CONCURRENCY)
    futures = []

    for rcw_msrmt in rcw_mapping.keys():
        futures.append(asyncio.create_task(read_single_measurement(semaphore, rcw_msrmt, since, to)))
    return await asyncio.gather(*futures, return_exceptions=True)


if __name__ == '__main__':
    print('Alive:', loop.run_until_complete(client.service.ServerAlive()))
    # print('Check Creds:', client.service.CheckCredentials(creds))

    while True:
        start = time.time()
        results = loop.run_until_complete(read_rcware_measurements(datetime.utcnow() - timedelta(minutes=5)))
        exceptions = [r for r in results if isinstance(r, Exception)]
        if exceptions:
            print(exceptions[0])
        print(int(start), len(results), "dps done in", f'{time.time() - start:.2f}s', f'exceptions: {len(exceptions)}')
        # print(results)

        # influxdb.create_database('rcware_test')
        # influxdb.switch_database('rcware_test')
        # influxdb.write_points(data)

        time.sleep(300 - (time.time() - start))

    # loop.run_until_complete(transport.session.close())