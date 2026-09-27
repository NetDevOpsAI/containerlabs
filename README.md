# Containerlabs

A collection of Containerlab network labs for quick testing and validation.

The first lab started when I needed a quick SRv6 lab to validate something. I found a LinkedIn post by Matt Leuschner, took the topology picture, and gave it to Claude Sonnet 5 with a short instruction: build the lab as shown, create all the configs, test everything, and document it.

About 30 minutes later, AI had built, tested, and documented the lab. All from one picture and a short instruction.

## Labs

| Lab | Description | Documentation |
| --- | --- | --- |
| [lab-srv6](lab-srv6/) | SRv6 lab using Cisco IOL routers. Includes the topology, router configs, and verification script. | [Lab guide](lab-srv6/HLD.md) |
| [lab-sr-mpls](lab-sr-mpls/) | SR-MPLS lab using the same topology as lab-srv6. | [Lab guide](lab-sr-mpls/HLD.md) |
