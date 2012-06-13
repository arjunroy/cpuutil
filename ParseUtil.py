#!/usr/bin/python

import re

def getBlocksFromFile(filename):
    handle = open(filename, "r")
    
    blocklist = []
    currentblock = []

    # Read blocks. Each block is one output, separated from former and 
    # succeeding blocks by the configured interval.
    for line in handle:
        # If line starts with "Linux", skip
        if line[0:5] == "Linux":
            continue
        line = line.rstrip()
        if len(line) != 0:
            currentblock.append(line)
        else:
            if len(currentblock) != 0:
                blocklist.append(currentblock)
            currentblock = []

    if len(currentblock) != 0:
        blocklist.append(currentblock)
    handle.close()
    return blocklist

def processUsageFile(filename, usageList):
    blocklist = getBlocksFromFile(filename)
    for block in blocklist:
        processUsageBlock(block, usageList)

def processUsageBlock(block, usageList):
    headerRegex = re.compile("\d\d:\d\d:\d\d\s+(?:AM|PM)\s+CPU\s+(.*)")
    regex = re.compile("\d\d:\d\d:\d\d\s+(?:AM|PM)\s+(all|\d+)(.*)")
    keys = None
    usageEntry = {}
    
    for line in block:
        match = regex.match(line)
        header = headerRegex.match(line)
        if header is not None and keys is not None:
            raise "Multiple headers found in block!"
        if header is not None:
            keys = header.group(1).split()
        if match is not None:
            cpuid = match.group(1)
            data = match.group(2).split()
            usageEntry[cpuid] = zip(keys, data)

    usageList.append(usageEntry)

