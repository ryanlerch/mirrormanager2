"""
Synchronize Amazon AWS-published EC2 netblock lists per region into the
MirrorManager database for Fedora Infrastructure-managed mirrors in S3.
"""

import click
import requests

import mirrormanager2.lib
from mirrormanager2.lib.database import get_db_manager
from mirrormanager2.lib.model import HostNetblock

from .common import config_option


def parse_out_region(hostname):
    if hostname.startswith("s3-mirror-"):
        hostname = hostname[len("s3-mirror-") :]
    if hostname.endswith(".fedoraproject.org"):
        hostname = hostname[: -len(".fedoraproject.org")]
    return hostname


def s3_mirrors(session):
    hosts_by_region = {}
    site = mirrormanager2.lib.get_site_by_name(session, "Red Hat")
    for host in site.hosts:
        if host.name.startswith("s3"):
            region = parse_out_region(host.name)
            hosts_by_region[region] = {
                "host": host,
                "netblocks": {},
            }
            for nb in host.netblocks:
                hosts_by_region[region]["netblocks"][nb.netblock] = {
                    "host_netblock_id": nb.id,
                    "stale": True,
                }
    return hosts_by_region


def get_ip_ranges():
    response = requests.get("https://ip-ranges.amazonaws.com/ip-ranges.json")
    response.raise_for_status()
    return response.json()


def host_has_netblock(hosts_by_region, region, netblock):
    return netblock in hosts_by_region[region]["netblocks"]


def doit(session, dry_run):
    hosts_by_region = s3_mirrors(session)
    ipranges = get_ip_ranges()

    for p in ipranges["prefixes"]:
        service = p["service"]
        region = p["region"]
        ip_prefix = p["ip_prefix"]
        if service != "EC2":
            continue
        if region == "GLOBAL":
            continue

        if region in hosts_by_region:  # ignore regions we don't have a mirror in
            h = hosts_by_region[region]
            host = h["host"]
            if not host_has_netblock(hosts_by_region, region, ip_prefix):
                print(f"Adding host {host.name} netblock {ip_prefix}")
                if not dry_run:
                    nb = HostNetblock(
                        host=host, netblock=ip_prefix, name=None
                    )  # this adds the entry to the database, mark as not stale
                    session.add(nb)
                    session.flush()
                    hosts_by_region[region]["netblocks"][ip_prefix] = {
                        "host_netblock_id": nb.id,
                        "stale": False,
                    }
            else:
                # found the netblock in our database, mark it as not stale
                hosts_by_region[region]["netblocks"][ip_prefix]["stale"] = False

    # delete stale netblock entries from the database
    for region, h in hosts_by_region.items():
        for netblock in hosts_by_region[region]["netblocks"]:
            if hosts_by_region[region]["netblocks"][netblock][
                "stale"
            ]:  # delete this, it's no longer on Amazon's list
                host = h["host"]
                print(f"Deleting host {host.name} netblock {netblock}")
                if not dry_run:
                    nb = mirrormanager2.lib.get_host_netblock(
                        session, hosts_by_region[region]["netblocks"][netblock]["host_netblock_id"]
                    )
                    session.delete(nb)


@click.command()
@config_option
@click.option("-n", "--dry-run", is_flag=True, default=False)
def main(config, dry_run):
    config = mirrormanager2.lib.read_config(config)
    db_manager = get_db_manager(config)
    with db_manager.Session() as session:
        doit(session, dry_run)
        session.commit()
