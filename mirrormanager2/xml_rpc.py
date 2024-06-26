# Copyright © 2014  Red Hat, Inc.
#
# This copyrighted material is made available to anyone wishing to use,
# modify, copy, or redistribute it subject to the terms and conditions
# of the GNU General Public License v.2, or (at your option) any later
# version.  This program is distributed in the hope that it will be
# useful, but WITHOUT ANY WARRANTY expressed or implied, including the
# implied warranties of MERCHANTABILITY or FITNESS FOR A PARTICULAR
# PURPOSE.  See the GNU General Public License for more details.  You
# should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation,
# Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
#
# Any Red Hat trademarks that are incorporated in the source
# code or documentation are not subject to the GNU General Public
# License and may only be used or replicated with the express permission
# of Red Hat, Inc.
#

"""
MirrorManager2 xmlrpc controller.
"""

import base64
import bz2
import json
import logging
import pickle

from mirrormanager2.database import DB
from mirrormanager2.lib.hostconfig import read_host_config

try:
    from flask_xmlrpcre.xmlrpcre import XMLRPCHandler
except ImportError:
    # flask-xml-rpc is patched in Fedora, and flask-xml-rpc-re is not packaged.
    from flaskext.xmlrpc import XMLRPCHandler

logger = logging.getLogger(__name__)

XMLRPC = XMLRPCHandler("xmlrpc")


@XMLRPC.register
def checkin(pickledata):
    is_pickle = False
    uncompressed = bz2.decompress(base64.urlsafe_b64decode(pickledata))
    try:
        config = json.loads(uncompressed)
    except ValueError:
        logging.info("Fell back to pickle")
        is_pickle = True
        config = pickle.loads(uncompressed)
    r, host, message = read_host_config(DB.session, config)
    if r is not None:
        logging.info(f"Checkin for host {host} (pickle:{is_pickle}) succesful: {message}")
        return message + "checked in successful"
    else:
        logging.error(f"Error for host {host} (pickle:{is_pickle}) during checkin: {message}")
        return message + "error checking in"
