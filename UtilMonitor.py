#!/usr/bin/python

'''
mpstat wrapper that polls for statistics in a given interval from a specific
start time (in epoch seconds) till an end time, or for a specified number of
seconds. If no end time is specified, grabs data until specifically cancelled.
'''

import time, threading, subprocess
import cpuutil.ParseUtil

# Each stats object is just a container for values. The UsageCollector does
# the job of actually collecting the necessary statistics.

class UsageCollector:
    '''
    On init, runs a copy of mpstat which outputs to a file.
    On shutdown, kills the mpstat process that it started, parses
    the file and stores the parsed data in memory.
    '''
    def __init__(self, monitor):
        self.monitor = monitor

        self.usageFile = open(self.monitor.fileprefix + "_usage.txt", "a")
        self.irqFile = open(self.monitor.fileprefix + "_irq.txt", "a")
        self.softIrqFile = open(self.monitor.fileprefix + "_softirq.txt", "a")
        self.irqSumFile = open(self.monitor.fileprefix + "_sum.txt", "a")

        self.usageProcess = subprocess.Popen(["mpstat", "-P", "ALL", "-u", \
            str(self.monitor.interval)], stdout = self.usageFile)

        self.irqProcess = subprocess.Popen(["mpstat", "-P", "ALL", "-I", "CPU", \
            str(self.monitor.interval)], stdout = self.irqFile)

        self.softIrqProcess = subprocess.Popen(["mpstat", "-P", "ALL", "-I", "SCPU",\
            str(self.monitor.interval)], stdout = self.softIrqFile)

        self.sumProcess = subprocess.Popen(["mpstat", "-P", "ALL", "-I", "SUM",\
            str(self.monitor.interval)], stdout = self.irqSumFile)

    def shutdown(self):
        self.usageProcess.kill()
        self.irqProcess.kill()
        self.softIrqProcess.kill()
        self.sumProcess.kill()

        self.usageFile.close()
        self.irqFile.close()
        self.softIrqFile.close()
        self.irqSumFile.close()

        self.processResults()

    def processResults(self):
        self.processUsageFile()
        self.processIrqFile()
        self.processSoftIrqFile()
        self.processIrqSumFile()

    def processDataFile(self, filename, outputlist):
        scratchList = []
        cpuutil.ParseUtil.processUsageFile(filename, scratchList)
        currTime = self.monitor.startTime
        for entry in scratchList:
            outputlist.append((currTime, entry))
            currTime += self.monitor.interval

    def processUsageFile(self):
        self.processDataFile(self.monitor.fileprefix + "_usage.txt", \
            self.monitor.usageStats)

    def processIrqFile(self):
        self.processDataFile(self.monitor.fileprefix + "_irq.txt", \
            self.monitor.irqStats)

    def processSoftIrqFile(self):
        self.processDataFile(self.monitor.fileprefix + "_softirq.txt", \
            self.monitor.softIrqStats)

    def processIrqSumFile(self):
        self.processDataFile(self.monitor.fileprefix + "_sum.txt", \
            self.monitor.irqSumStats)

class UtilMonitor(threading.Thread):
    def __init__(self, startTime = None, \
                       endTime = None, \
                       numSeconds = None, \
                       interval = None,\
                       fileprefix = "default"):
        # Only one of endTime and numSeconds can be set
        if endTime is not None and numSeconds is not None:
            raise "Only one of endTime and numSeconds can be set!"

        threading.Thread.__init__(self)
        self.startTime = startTime
        self.endTime = endTime
        self.numSeconds = numSeconds
        self.interval = interval
        self.fileprefix = fileprefix

        self.lock = threading.Lock()

        if self.startTime is None:
            self.startTime = int(time.time())
        if self.endTime is None and self.numSeconds is not None:
            self.endTime = self.startTime + self.numSeconds
        if self.interval is None:
            self.interval = 1

        # Array indexed by time, containg tuples of (time, statobj)
        # where statobj is one of usagestats, irqstats, softirqstats
        self.usageStats = []
        self.irqStats = []
        self.softIrqStats = []
        self.irqSumStats = []

    def run(self):
        self.collectData()

    def collectData(self):
        '''
        Main loop: If we're within the timeframe for collection, which starts
        >= startTime and ends <= endTime where endTime might be unspecified and
        thus infinite, keep collecting data.

        If our time frame has ended, stop collecting. The time frame can be set
        while we run.
        '''
        self.lock.acquire()
        endTime = self.endTime
        self.lock.release()

        if endTime is not None and endTime < self.startTime:
            # We don't collect at all.
            return 0

        # Wait until start time.
        now = int(time.time())
        if self.startTime > now:
            time.sleep(self.startTime - now)

        # Now, we're at start time, end time either unspecified or in the
        # future, so we're ready to start collecting.
        collector = UsageCollector(self)

        if endTime is None:
            # Do we keep running?
            while(True):
                self.lock.acquire()
                endTime = self.endTime
                self.lock.release()
                if endTime is not None and int(time.time()) >= endTime:
                    break
                # Check every second
                time.sleep(1)
        else:
            # Only poll if we have to.
            time.sleep(self.endTime - self.startTime)

        collector.shutdown()
        return 0

    def stopCollection(self):
        self.lock.acquire()
        self.endTime = self.startTime - 1
        self.lock.release()
        return 0

    def stopCollectionAt(self, endTime):
        self.lock.acquire()
        self.endTime = endTime
        self.lock.release()
        return 0

    def __getAverageStats(self, startTime, endTime, numSeconds, statsList):
        if endTime is not None and numSeconds is not None:
            raise "Cannot specify both endtime and numseconds!"

        if startTime is None:
            startTime = self.startTime
        if endTime is None:
            if numSeconds is not None:
                endTime = startTime + numSeconds
            else:
                endTime = self.endTime + 10 # Safety margin HAX
        entries = [stat[1] for stat in statsList if stat[0] >= startTime and stat[0] <= endTime]
        numEntries = len(entries)

        accumulator = {}
        for entry in entries:
            for cpuid in  entry.keys():
                if cpuid not in accumulator:
                    accumulator[cpuid] = {}
                cpudata = accumulator[cpuid]
                currentData = entry[cpuid]
                for pair in currentData:
                    if pair[0] not in cpudata:
                        cpudata[pair[0]] = float(pair[1])
                    else:
                        cpudata[pair[0]] += float(pair[1])

        for cpuid in accumulator.keys():
            cpudata = accumulator[cpuid]
            for key in cpudata.keys():
                cpudata[key] /= len(entries)

        return accumulator

    def getAverageUsageStats(self, startTime = None, endTime = None, numSeconds = None):
        return self.__getAverageStats(startTime, endTime, numSeconds, self.usageStats)

    def getAverageIRQStats(self, startTime = None, endTime = None, numSeconds = None):
        return self.__getAverageStats(startTime, endTime, numSeconds, self.irqStats)

    def getAverageSoftIRQStats(self, startTime = None, endTime = None, numSeconds = None):
        return self.__getAverageStats(startTime, endTime, numSeconds, self.softIrqStats)

    def getAverageIRQSumStats(self, startTime = None, endTime = None, numSeconds = None):
        return self.__getAverageStats(startTime, endTime, numSeconds, self.irqSumStats)

