## Create Config File for Cert creation
Here is the format for the cert config file:
[ req ]
default_bits       = 2048
prompt              = no
distinguished_name  = dn
req_extensions      = req_ext

[ dn ]
CN = homeassistant.home.arpa

[ req_ext ]
subjectAltName = @alt_names

[ alt_names ]
DNS.1 = homeassistant.home.arpa
DNS.2 = homeassistant
DNS.3 = homeassistant.local
IP.1  = 192.168.1.50


## Generate Key & CSR
# This is an example with homeassistant (ha)
openssl genrsa -out private/ha.key 2048
openssl req -new -config ha.cnf -key private/ha.key -out csr/ha.csr

## Sign it with the CA (need the SAN extension carried through, so use -extfile):
openssl x509 -req -in csr/ha.csr \
  -CA root-ca/root-ca.crt -CAkey private/root-ca.key -CAcreateserial \
  -out certs/ha.crt -days 825 -sha256 \
  -extfile ha.cnf -extensions req_ext


## Sonarr and Radarr need pfx format
openssl pkcs12 -export -out sonarr.pfx \
    -inkey private/sonarr.key -in certs/sonarr.crt \
    -certfile root-ca/root-ca.crt
