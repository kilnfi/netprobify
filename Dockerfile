#
# HOWTO
#
# Build the image: docker build . -t netprobify
#
# Run the image: docker run -it --rm --network host -v "$PWD/config.yaml":/opt/netprobify/config.yaml --name "netprobify" netprobify
#

FROM python:3.9

# Install system dependencies
RUN apt update && apt install -y tcpdump && apt clean

# Install python dependencies - done copying the code to leverage caching
WORKDIR /opt/netprobify
COPY requirements /opt/netprobify/requirements
RUN pip install -r requirements/netprobify.txt

# Copy the source code
COPY netprobify /opt/netprobify/netprobify
COPY netprobify_start.py /opt/netprobify/
COPY VERSION /opt/netprobify/

# All done, we can start!
CMD [ "python", "/opt/netprobify/netprobify_start.py" ]
