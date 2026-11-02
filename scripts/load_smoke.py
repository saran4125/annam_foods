"""Bounded GET-only smoke test. Run only against a deployment you control."""
import argparse,json,statistics,time,urllib.request
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlsplit


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--base-url',default='http://127.0.0.1:8112')
    parser.add_argument('--requests',type=int,default=100)
    parser.add_argument('--concurrency',type=int,default=8)
    options=parser.parse_args()
    if not 1<=options.requests<=2000 or not 1<=options.concurrency<=32:parser.error('Use 1–2000 requests and 1–32 concurrent requests.')
    url=urlsplit(options.base_url)
    if url.scheme not in ('http','https') or not url.netloc:parser.error('Use an HTTP(S) deployment URL.')
    paths=['/shop/','/shop/podi/','/healthz']
    def request(index):
        started=time.perf_counter();path=paths[index%len(paths)]
        try:
            with urllib.request.urlopen(options.base_url.rstrip('/')+path,timeout=15) as response:
                response.read();ok=response.status==200
        except Exception:ok=False
        return {'path':path,'ok':ok,'ms':round((time.perf_counter()-started)*1000,2)}
    began=time.perf_counter()
    with ThreadPoolExecutor(max_workers=options.concurrency) as workers:results=list(workers.map(request,range(options.requests)))
    times=sorted(row['ms'] for row in results)
    report={'requests':len(results),'concurrency':options.concurrency,'errors':sum(not r['ok'] for r in results),
            'elapsed_seconds':round(time.perf_counter()-began,2),'median_ms':round(statistics.median(times),2),
            'p95_ms':times[min(len(times)-1,int(len(times)*0.95))],
            'scope':'GET-only smoke check; not a production capacity guarantee'}
    print(json.dumps(report,indent=2))
    return 1 if report['errors'] else 0


if __name__=='__main__':raise SystemExit(main())
