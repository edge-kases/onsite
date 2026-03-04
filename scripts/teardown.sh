#!/bin/bash
echo "Deleting namespaces..."
kubectl delete namespace tenant-acme tenant-globex phylo-system --ignore-not-found
echo "Done."
