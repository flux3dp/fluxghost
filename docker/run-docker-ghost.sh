cd $(dirname $0)
cd ..
docker run -v .:/code/fluxghost \
  --rm -p 8000:8000 fluxghost python fluxghost/ghost.py --allow-foreign --ip 0.0.0.0
