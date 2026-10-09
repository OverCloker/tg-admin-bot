"""Read-only live source checks, no bot actions."""
import asyncio
import json
import sys
from app.power_outages import locations, options, schedule

async def main():
    for q in ['Кривий Ріг', 'Київ']:
        print(q, json.dumps(await locations(q), ensure_ascii=False))
    for p in ['/dnipropetrovska-oblast/krivij-rig', '/kyiv', '/poltavska-oblast/cutivska-hromada/cutove', '/cherkaska-oblast/cerkasi']:
        try:
            values = await options(p)
            graph = await schedule(p, values['groups'][0])
            print(p, values, 'published:', graph['published'], 'intervals:', len(graph['intervals']), 'source:', graph['sourceUrl'])
        except Exception as exc:
            print(p, type(exc).__name__, str(exc))

if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    asyncio.run(main())
