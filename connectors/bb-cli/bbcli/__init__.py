"""bbcli — CUHK-SZ Blackboard read-only CLI connector.

Layering: config (paths and settings) / transport (curl_cffi session and TLS
fingerprint) / auth (ADFS OAuth2 login) / api (Learn REST wrappers) / cli
(command surface).
Discipline: read-only — never issues any write request; credentials and
sessions live only in the user directory, never in any repository.
"""

__version__ = "0.2.0"
