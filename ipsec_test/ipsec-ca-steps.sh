#!/bin/bash

source env.sh

# Check if the 'openssl' command is available in the system's PATH
if command -v openssl &> /dev/null
then
    echo "OpenSSL is installed."
    openssl version
else
    echo "OpenSSL is not installed or not found in the PATH."
    exit 1
fi


HOSTS=("hostA" "hostB")

# Check if the namespace exists
for HOST in "${HOSTS[@]}"; do
    if ip netns list | grep -q "$HOST"; then
        echo "Network namespace '$HOST' exists."
    else
        echo "Network namespace '$HOST' does not exist."
        exit 1
    fi
done

 
# CA and host certificates for IPsec testing with strongSwan

cd $HOST_DIR/ipsec_test
echo "Creating CA and host certificates for IPsec testing with strongSwan in $HOST_DIR"

mkdir -p ipsec-ca
cd ipsec-ca

# CA private key
openssl genrsa -out ca.key 4096

# CA certificate
openssl req -x509 -new -nodes \
  -key ca.key \
  -sha256 -days 3650 \
  -subj "/CN=IPsec-Test-CA" \
  -out ca.crt

# Host A

cd $HOST_DIR/ipsec_test/ipsec-ca

openssl genrsa -out hostA.key 3072

openssl req -new \
  -key hostA.key \
  -subj "/CN=hostA" \
  -out hostA.csr

openssl x509 -req \
  -in hostA.csr \
  -CA ca.crt -CAkey ca.key -CAcreateserial \
  -out hostA.crt -days 365 -sha256

# HostB:

cd $HOST_DIR/ipsec_test/ipsec-ca

openssl genrsa -out hostB.key 3072

openssl req -new \
  -key hostB.key \
  -subj "/CN=hostB" \
  -out hostB.csr

openssl x509 -req \
  -in hostB.csr \
  -CA ca.crt -CAkey ca.key -CAcreateserial \
  -out hostB.crt -days 365 -sha256
