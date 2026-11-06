"""Pure bounded forbidden-port probe; refusal is not a positive isolation result."""
import ipaddress,socket

def probe_denied_port(host,port,connect=None):
    assert ipaddress.ip_address(host).is_private and port==29501,'outside fixed pair probe scope'
    connect=connect or socket.create_connection
    try:conn=connect((host,port),timeout=2)
    except TimeoutError:return {'denied':True,'port':port,'observation':'timeout','timeout_seconds':2}
    else:
        conn.close()
        raise AssertionError('forbidden inter-Pod TCP port is reachable')
