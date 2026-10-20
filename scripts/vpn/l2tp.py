"""Optional owner-operated L2TP/IPsec PSK transport. No plan-site requests."""
from __future__ import annotations
import ipaddress
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import time
from collections.abc import Mapping

STAGE='initializing'
DIAGNOSTICS: dict[str,object] = {}
READINESS: dict[str,object] = {}

def stage(name: str) -> None:
    global STAGE
    STAGE=name

ROOT=Path('/run/mavat-l2tp')

class TunnelError(Exception):
    """Only constant, non-private diagnostics may reach Actions logs."""

def summarize_negotiation(text: str) -> dict[str,object]:
    """Convert raw private daemon text into fixed categories only, never interpolate."""
    low=text.lower()
    classes={
        'connection_not_loaded': ('no config named','no connection named'),
        'daemon_unavailable': ('connecting to stroke socket failed','connection refused','charon is not running','starter is not running','failed to connect to'),
        'proposal_mismatch': ('no proposal chosen','no_proposal_chosen','no acceptable proposal'),
        'authentication_failed': ('authentication failed','authentication_failed','invalid hash'),
        'peer_no_response': ('peer not responding','giving up after','retransmit'),
        'ike_established': ('isakmp sa established',),
        'child_established': ('ipsec sa established',),
        'nat_detected': ('behind nat','nat detected'),
        'nat_t_port_observed': ('[4500]','port 4500'),
        'kernel_failure': ('failed to install','operation not supported','protocol not supported'),
    }
    found=[name for name,phrases in classes.items() if any(p in low for p in phrases)]
    if re.search(r'ike_sa[^\n]*established',low):found.append('ike_established')
    if re.search(r'child_sa[^\n]*established',low):found.append('child_established')
    found=sorted(set(found))
    if re.search(r'(?:received|parsed)[^\n]*(?:NO_PROPOSAL_CHOSEN|N\(NO_PROP\))',text,re.I):
        found.append('peer_no_proposal_notification')
    sent=re.findall(r'generating (ID_PROT|QUICK_MODE|INFORMATIONAL|TRANSACTION)(?:_V1)?[^\n]*?request',text,re.I)
    parsed=re.findall(r'parsed (ID_PROT|QUICK_MODE|INFORMATIONAL|TRANSACTION)(?:_V1)?[^\n]*?(?:request|response)',text,re.I)
    saw_reply=bool(parsed) or 'peer_no_proposal_notification' in found
    return {'classes':sorted(set(found)),'retransmit_count':len(re.findall(r'\bretransmit\b',low)),
            'generated_request_classes':sorted({x.upper() for x in sent}),
            'parsed_response_classes':sorted({x.upper() for x in parsed}),
            'request_without_observed_response':[] if saw_reply else sorted({x.upper() for x in sent}),
            'peer_reply_observed':saw_reply}

def run(*args: str, check: bool=True) -> str:
    result=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=60)
    if STAGE=='ipsec_negotiate' and 'up' in args:
        DIAGNOSTICS.update(summarize_negotiation((result.stdout or '')+'\n'+(result.stderr or '')))
    if check and result.returncode:
        raise TunnelError('command_exit_'+str(result.returncode))
    return result.stdout.strip()

def readiness_snapshot(status: str) -> dict[str,bool]:
    """No process IDs, addresses, status text or connection details may be returned."""
    pid=Path('/run/charon.pid')
    alive=False
    if pid.exists():
        try:
            os.kill(int(pid.read_text().strip()),0)
            alive=True
        except (OSError,ValueError):pass
    return {'charon_pid_file_present':pid.exists(),'charon_process_alive':alive,
            'control_socket_present':Path('/run/charon.ctl').exists(),
            'connection_loaded':bool(re.search(r'^\s*mavat-l2tp:\s+.*IKEv1',status,re.M))}

def wait_ready(limit: int=15) -> None:
    """Bounded local control-plane readiness, never initiate a negotiation here."""
    for index in range(limit):
        status=''
        try:status=run('timeout','3','ipsec','statusall')
        except Exception:pass
        READINESS.update(readiness_snapshot(status))
        READINESS['checks']=index+1
        if all(READINESS[key] for key in ['charon_pid_file_present','charon_process_alive','control_socket_present','connection_loaded']):
            print(json.dumps({'status':'vpn_control_ready','readiness':dict(READINESS),'mavat_requests':0}),flush=True)
            return
        if index+1<limit:time.sleep(1)
    raise TunnelError('Local IPsec control not ready')

def established_snapshot(status: str) -> dict[str,bool]:
    """Require both an established IKE SA and installed transport CHILD SA."""
    return {'ike_sa_established':bool(re.search(r'^\s*mavat-l2tp\[\d+\]:\s+ESTABLISHED\b',status,re.M)),
            'transport_sa_installed':bool(re.search(r'^\s*mavat-l2tp\{\d+\}:\s+INSTALLED,\s+TRANSPORT\b',status,re.M))}

def require_established() -> None:
    status=run('timeout','3','ipsec','statusall')
    state=established_snapshot(status)
    DIAGNOSTICS.update(state)
    if not all(state.values()):
        raise TunnelError('IPsec SA not established; no L2TP permitted')
    print(json.dumps({'status':'vpn_ipsec_established','ipsec':state,'mavat_requests':0}),flush=True)

def quote(value: str) -> str:
    if not value or any(ord(c)<32 or ord(c)>126 for c in value):
        raise TunnelError('VPN credential format unsupported')
    return '"'+value.replace('\\','\\\\').replace('"','\\"')+'"'

def settings(env: Mapping[str,str]) -> tuple[str,str,str,str]:
    server=env.get('VPN_L2TP_SERVER','')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.-]{0,252}',server):
        raise TunnelError('VPN server must be a hostname or IPv4 address, not a URL')
    return server,quote(env.get('VPN_L2TP_PSK','')),quote(env.get('VPN_L2TP_USERNAME','')),quote(env.get('VPN_L2TP_PASSWORD',''))

def configs(server: str,psk: str,user: str,password: str) -> dict[str,str]:
    return {
        'ipsec.conf': f'''config setup
conn mavat-l2tp
    keyexchange=ikev1
    ike=aes256-sha256-modp2048,aes128-sha256-modp2048,aes256-sha1-modp2048,aes128-sha1-modp2048!
    esp=aes256-sha256,aes128-sha256,aes256-sha1,aes128-sha1!
    authby=psk
    type=transport
    left=%defaultroute
    leftprotoport=17/1701
    right={server}
    rightprotoport=17/1701
    forceencaps=yes
    keyingtries=1
    rekey=no
    ikelifetime=8h
    lifetime=8h
    auto=add
''',
        'ipsec.secrets': ': PSK '+psk+'\n',
        'xl2tpd.conf': f'''[global]
force userspace = yes
port = 1701
[lac mavat]
lns = {server}
ppp debug = no
pppoptfile = /run/mavat-l2tp/ppp-options
length bit = yes
redial = no
''',
        'ppp-options': f'''ipcp-accept-local
ipcp-accept-remote
refuse-eap
refuse-pap
refuse-chap
refuse-mschap
require-mschap-v2
noauth
noccp
nodefaultroute
noipdefault
mtu 1400
mru 1400
maxfail 1
unit 43
name {user}
password {password}
connect-delay 5000
''',
        'strongswan.conf': """charon {
  plugins {
    bypass-lan { load = no }
  }
  syslog {
    daemon { default = -1 }
    auth { default = -1 }
  }
  filelog {
    private_diagnostics {
      path = /run/mavat-l2tp/charon-private.log
      default = 1
      flush_line = yes
      ike_name = no
      append = no
    }
  }
}
"""
    }

def down() -> None:
    if not ROOT.exists():
        return  # Disabled/not-started workflow must not touch host configuration.
    # Never print routes, peer addresses, config or daemon output.
    for cmd in [('ip','route','del','0.0.0.0/1','dev','ppp43'),('ip','route','del','128.0.0.0/1','dev','ppp43'),
                ('ipsec','down','mavat-l2tp'),('systemctl','stop','xl2tpd'),('ipsec','stop')]:
        try:run(*cmd,check=False)
        except Exception:pass
    # Remove only our firewall chains, not unrelated host policy.
    for binary in ['iptables','ip6tables']:
        for cmd in [(binary,'-D','OUTPUT','-p','tcp','--dport','443','-j','MAVATTLS'),
                    (binary,'-F','MAVATTLS'),(binary,'-X','MAVATTLS')]:
            try:run(*cmd,check=False)
            except Exception:pass
    if ROOT.exists():
        try:
            state=json.loads((ROOT/'state.json').read_text())
            run('ip','route','del',state['server']+'/32',check=False)
        except Exception:pass
    # Hosted runners are disposable. Delete all generated secret/config material.
    for path in ['/etc/ipsec.secrets','/etc/ipsec.conf','/etc/xl2tpd/xl2tpd.conf','/etc/strongswan.conf']:
        try:Path(path).unlink(missing_ok=True)
        except OSError:pass
    shutil.rmtree(ROOT,ignore_errors=True)

def up(env: Mapping[str,str]) -> None:
    DIAGNOSTICS.clear()
    READINESS.clear()
    stage('validate_settings')
    server,psk,user,password=settings(env)
    stage('resolve_vpn_server')
    answers=socket.getaddrinfo(server,None,socket.AF_INET,socket.SOCK_DGRAM)
    address=str(ipaddress.IPv4Address(answers[0][4][0]))
    stage('create_private_directory')
    ROOT.mkdir(mode=0o700,parents=True,exist_ok=False)
    os.umask(0o077)
    # Pin VPN transport outside the tunnel so the default route cannot loop.
    stage('read_transport_route')
    route=json.loads(run('ip','-json','route','get',address))[0]
    args=['ip','route','add',address+'/32']
    if route.get('gateway'):args+=['via',route['gateway']]
    args+=['dev',route['dev']]
    stage('pin_transport_route')
    run(*args)
    (ROOT/'state.json').write_text(json.dumps({'server':address}))
    destinations={'ipsec.conf':Path('/etc/ipsec.conf'),'ipsec.secrets':Path('/etc/ipsec.secrets'),
                  'xl2tpd.conf':Path('/etc/xl2tpd/xl2tpd.conf'),'strongswan.conf':Path('/etc/strongswan.conf'),
                  'ppp-options':ROOT/'ppp-options'}
    stage('write_private_config')
    for name,content in configs(address,psk,user,password).items():
        dest=destinations[name];dest.parent.mkdir(parents=True,exist_ok=True);dest.write_text(content);dest.chmod(0o600)
    # Kill switch: every HTTPS effect (including private ledger) must use PPP.
    # IPv6 HTTPS is rejected so no IPv6 route can bypass this IPv4-only profile.
    stage('install_https_killswitch')
    for binary in ['iptables','ip6tables']:
        run(binary,'-N','MAVATTLS')
        if binary=='iptables':run(binary,'-A','MAVATTLS','-o','ppp43','-j','RETURN')
        run(binary,'-A','MAVATTLS','-j','REJECT')
        run(binary,'-I','OUTPUT','1','-p','tcp','--dport','443','-j','MAVATTLS')
    stage('ipsec_daemon_start')
    run('ipsec','restart')
    stage('ipsec_wait_ready')
    wait_ready()
    stage('ipsec_negotiate')
    run('timeout','55','ipsec','up','mavat-l2tp')
    stage('ipsec_verify_established')
    require_established()
    stage('l2tp_daemon_start')
    run('systemctl','restart','xl2tpd')
    stage('l2tp_control')
    control=Path('/var/run/xl2tpd/l2tp-control')
    if not control.exists():raise TunnelError('L2TP control unavailable')
    with control.open('w') as stream:stream.write('c mavat\n')
    stage('ppp_wait')
    for _ in range(30):
        try:
            links=json.loads(run('ip','-json','address','show','dev','ppp43'))
            if any(a.get('family')=='inet' for l in links for a in l.get('addr_info',[])):break
        except TunnelError:pass
        time.sleep(1)
    else:raise TunnelError('VPN PPP did not become ready')
    stage('install_ppp_routes')
    run('ip','route','add','0.0.0.0/1','dev','ppp43')
    run('ip','route','add','128.0.0.0/1','dev','ppp43')
    # Resolve and verify routes without sending an HTTP/Login/report request.
    stage('verify_mavat_routes_without_request')
    targets=socket.getaddrinfo('mavat.iplan.gov.il',443,socket.AF_INET,socket.SOCK_STREAM)
    for target in {a[4][0] for a in targets}:
        check=json.loads(run('ip','-json','route','get',target))[0]
        if check.get('dev')!='ppp43':raise TunnelError('Mavat route did not select VPN')

def safe_failure(error: Exception) -> str:
    if isinstance(error,subprocess.TimeoutExpired):return 'command_timeout'
    if isinstance(error,socket.gaierror):return 'dns_resolution_failed'
    if isinstance(error,TunnelError):
        value=str(error)
        return value if re.fullmatch(r'command_exit_[0-9]+',value) else 'stage_validation_failed'
    if isinstance(error,OSError):return 'os_error_'+str(error.errno or 0)
    return 'unexpected_error'

def connect_bounded(env: Mapping[str,str], attempts: int=3) -> None:
    """Only tunnel bring-up may retry. Caller invokes municipal flow once afterwards."""
    if attempts not in (1,3):raise TunnelError('Unsupported attempt count')
    delays=(60,300)
    for attempt in range(1,attempts+1):
        try:
            up(env)
            print(json.dumps({'status':'vpn_connected','attempt':attempt,'mavat_requests':0}),flush=True)
            return
        except Exception as error:
            failed_stage=STAGE
            diagnostic=safe_failure(error)
            log=ROOT/'charon-private.log'
            if log.exists():
                try:
                    combined=summarize_negotiation(log.read_text(errors='replace')[-131072:])
                    combined['classes']=sorted(set(combined['classes'])|set(DIAGNOSTICS.get('classes',[])))
                    for key in ['generated_request_classes','parsed_response_classes','request_without_observed_response']:
                        combined[key]=sorted(set(combined[key])|set(DIAGNOSTICS.get(key,[])))
                    combined['retransmit_count']=max(combined['retransmit_count'],DIAGNOSTICS.get('retransmit_count',0))
                    combined['peer_reply_observed']=bool(combined['peer_reply_observed'] or DIAGNOSTICS.get('peer_reply_observed',False))
                    if combined['peer_reply_observed']:combined['request_without_observed_response']=[]
                    DIAGNOSTICS.update(combined)
                except Exception:pass
            down()
            print(json.dumps({'status':'vpn_failed','stage':failed_stage,'diagnostic':diagnostic,
                              'attempt':attempt,'readiness':dict(READINESS),'negotiation':dict(DIAGNOSTICS),'mavat_requests':0}),flush=True)
            if attempt==attempts:
                raise TunnelError('VPN attempts exhausted; no municipal action permitted') from None
            wait=delays[attempt-1]
            print(json.dumps({'status':'vpn_backoff','seconds':wait,'next_attempt':attempt+1}),flush=True)
            time.sleep(wait)

def main() -> None:
    if os.geteuid()!=0:raise SystemExit('VPN helper requires the disposable Ubuntu runner sudo context')
    if sys.argv[1:]==['down']:
        down();return
    if sys.argv[1:] not in (['up'],['up-bounded']):raise SystemExit('Use up, up-bounded or down')
    try:connect_bounded(os.environ,3 if sys.argv[1:]==['up-bounded'] else 1)
    except Exception:
        raise SystemExit('Private VPN setup failed; no municipal action is permitted') from None

if __name__=='__main__':main()
