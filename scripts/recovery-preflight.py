#!/usr/bin/env python3
"""Read-only preflight for owner-approved database-only restore verification.

No dump, restore, mkdir, Docker run/create/start/stop/rm, network or volume
mutation. Capture diagnostics privately; print only decision metadata.
"""
import json
import shutil
import subprocess
from pathlib import Path

PAIRS = {
    'hub': ('v79-hub', 'v79-hub-postgres',
        'sha256:7876715a44166c1cbeb6b5070a774efb4d69fe36427bda1c4dee4fc637c67e30',
        'sha256:b0f9560a2de083e2cc7382e75f808c7381a32852a7ec49117deedb300e552b24'),
    'tiquet': ('v79-tiquet-manager', 'tiquet-postgres',
        'sha256:ee3deff332977160d66e0dbb448aef1e1e6d4418eac333e1feaf8a07c044715b',
        'sha256:cf78e76683b9ca8c5733cbbdce6c9262b45b6767934dd0a95e671f9a0fc20685'),
}

APP_PROBE = r'''
import pg from 'pg';
try { const d=await import('dotenv'); d.config({path:'/app/.env',quiet:true}); } catch {}
const hub=process.env.V79_RECOVERY_APP==='hub';
if(hub && (process.env.V79_HUB_STORE_BACKEND!=='postgres'||!process.env.DATABASE_URL)) process.exit(2);
const o={connectionTimeoutMillis:4000,query_timeout:5000,
 options:'-c default_transaction_read_only=on -c statement_timeout=5000 -c lock_timeout=1000'};
if(process.env.DATABASE_URL) o.connectionString=process.env.DATABASE_URL;
else Object.assign(o,{host:process.env.DB_HOST||'tiquet-postgres',port:Number(process.env.DB_PORT||5432),
 database:process.env.DB_NAME||'tiquet',user:process.env.DB_USER||'tiquet_app',password:process.env.DB_PASSWORD,
 ssl:process.env.DB_SSL==='true'?{rejectUnauthorized:false}:false});
const c=new pg.Client(o);
try {
 await c.connect(); await c.query('BEGIN READ ONLY');
 const r=await c.query(`SELECT current_database() AS db,inet_server_addr()::text AS addr,
  inet_server_port() AS port,pg_database_size(current_database())::text AS bytes,
  current_setting('server_version') AS version,current_setting('transaction_read_only') AS ro`);
 console.log(JSON.stringify(r.rows[0])); await c.query('ROLLBACK');
} catch { process.exitCode=2; }
finally { await c.end().catch(()=>{}); }
'''

DB_PROBE = r'''export PGPASSWORD="$POSTGRES_PASSWORD"
exec psql -X -q -A -t -v ON_ERROR_STOP=1 -h 127.0.0.1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
 -c "BEGIN READ ONLY; SELECT row_to_json(x) FROM (SELECT current_database() AS db,
 inet_server_port() AS port,current_setting('server_version') AS version,
 current_setting('transaction_read_only') AS ro) x; ROLLBACK;"
'''

def capture(args, payload=None):
    try:
        r = subprocess.run(args, input=payload, text=True, capture_output=True, timeout=25)
        return r.stdout if r.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None

def parsed(s):
    try:
        return json.loads(s) if s else None
    except (ValueError, TypeError):
        return None

def mapping_checks(app, target, db_container):
    app_ok=isinstance(app,dict) and bool(app.get('db')) and bool(app.get('version')) and isinstance(app.get('port'),int)
    target_ok=isinstance(target,dict) and bool(target.get('db')) and bool(target.get('version')) and isinstance(target.get('port'),int)
    addresses = {v.get('IPAddress') for v in db_container.get('NetworkSettings',{}).get('Networks',{}).values()}
    both=app_ok and target_ok
    return {'app_metadata_probe_available':bool(app_ok),
            'named_database_probe_available':bool(target_ok),
            'server_address_matches_named_container':bool(app_ok and app.get('addr') and app['addr'] in addresses),
            'database_name_matches':bool(both and app['db']==target['db']),
            'server_port_matches':bool(both and app['port']==target['port']),
            'server_version_matches':bool(both and app['version']==target['version']),
            'both_transactions_read_only':bool(both and app.get('ro')==target.get('ro')=='on')}

def mapping_matches(app, target, db_container):
    return all(mapping_checks(app,target,db_container).values())

def resource_checks(memory, free_disk, sizes, encryption):
    required = max(5*1024**3, 8*sum(sizes))
    return {'available_memory_mib': memory//1024**2,
            'available_disk_gib': free_disk//1024**3,
            'required_disk_gib_rounded_up': (required+1024**3-1)//1024**3,
            'memory_ok': memory >= 2*1024**3,
            'disk_ok': free_disk >= required,
            'encryption_tool_available': bool(encryption)}

def main():
    report={'read_only':True,'production':'NO-GO','backup_created':False,
            'restore_performed':False,'apps':{}}
    sizes=[]
    for name,(app_name,db_name,app_image,db_image) in PAIRS.items():
        ai=parsed(capture(['docker','inspect',app_name]))
        di=parsed(capture(['docker','inspect',db_name]))
        stable=bool(ai and di and ai[0].get('Image')==app_image and di[0].get('Image')==db_image
            and all(v[0].get('State',{}).get('Health',{}).get('Status')=='healthy' for v in (ai,di)))
        row={'expected_images_and_health':stable,'audit_connection_maps_to_named_db':False,
             'effective_running_pool_verified':False}
        if stable:
            a=parsed(capture(['docker','exec','-i','-e','V79_RECOVERY_APP='+name,
                app_name,'node','--input-type=module','-'],APP_PROBE))
            b=parsed(capture(['docker','exec','-i',db_name,'sh','-s'],DB_PROBE))
            row['mapping_checks']=mapping_checks(a,b,di[0])
            row['audit_connection_maps_to_named_db']=mapping_matches(a,b,di[0])
            if row['audit_connection_maps_to_named_db']:
                try:
                    size=int(a['bytes'])
                    if size < 0: raise ValueError()
                    sizes.append(size);row['database_size_mib_rounded_up']=(size+1024**2-1)//1024**2
                except (KeyError,ValueError,TypeError):
                    row['audit_connection_maps_to_named_db']=False
        report['apps'][name]=row
    try:
        mem=dict(line.split(':',1) for line in Path('/proc/meminfo').read_text().splitlines())
        available=int(mem['MemAvailable'].split()[0])*1024
        disk=shutil.disk_usage(Path.home()).free
        encryption=[name for name in ('gpg','age') if shutil.which(name)]
        report['resources']=resource_checks(available,disk,sizes,encryption)
        report['resources']['database_size_based_requirement_complete']=len(sizes)==2
        report['encryption_tools']=encryption
    except (OSError,KeyError,ValueError):
        report['resources']={'memory_ok':False,'disk_ok':False,'encryption_tool_available':False}
    report['preflight_checks_passed']=bool(len(sizes)==2 and
        all(r['expected_images_and_health'] and r['audit_connection_maps_to_named_db'] for r in report['apps'].values())
        and all(report['resources'].get(k) for k in ('memory_ok','disk_ok','encryption_tool_available')))
    report['effective_pool_and_backup_destination_review_required']=True
    print(json.dumps(report,indent=2,sort_keys=True))

if __name__=='__main__': main()
