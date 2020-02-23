from btchip.bitcoinTransaction import bitcoinTransaction, bitcoinInput, bitcoinOutput
from btchip.bitcoinVarint import *

from electrum.bitcoin import int_to_hex

import time

class eccoinTransaction(bitcoinTransaction):
	def __init__(self, data=None):
		self.version = ""
		self.timestamp = int_to_hex(int(time.time()), 4)
		self.inputs = []
		self.outputs = []
		self.lockTime = ""
		self.witness = False
		self.witnessScript = ""
		self.serviceHash = ""
		if data is not None:
			offset = 0
			self.version = data[offset:offset + 4]
			offset += 4
			self.timestamp = data[offset:offset + 4]
			offset += 4
			if (data[offset] == 0) and (data[offset + 1] != 0):
				offset += 2
				self.witness = True
			inputSize = readVarint(data, offset)
			offset += inputSize['size']
			numInputs = inputSize['value']
			for i in range(numInputs):
				tmp = { 'buffer': data, 'offset' : offset}
				self.inputs.append(bitcoinInput(tmp))
				offset = tmp['offset']
			outputSize = readVarint(data, offset)
			offset += outputSize['size']
			numOutputs = outputSize['value']
			for i in range(numOutputs):
				tmp = { 'buffer': data, 'offset' : offset}
				self.outputs.append(bitcoinOutput(tmp))
				offset = tmp['offset']
			if self.witness:
				self.witnessScript = data[offset : len(data) - 4]
				self.lockTime = data[len(data) - 4:]
				offset += 4
			else:
				self.lockTime = data[offset:offset + 4]
				offset += 4

			# read ECC service reference hash of version 2 txs
			if self.version != int_to_hex(int(1), 4):
				self.serviceHash = data[offset:offset + 32] # unused, just read it, necessary for serialization and txid calculation

	def serialize(self, skipOutputLocktime=False, skipWitness=False):
		if skipWitness or (not self.witness):
			useWitness = False
		else:
			useWitness = True
		result = []
		result.extend(self.version)
		result.extend(self.timestamp)
		if useWitness:
			result.append(0x00)
			result.append(0x01)
		writeVarint(len(self.inputs), result)
		for trinput in self.inputs:
			result.extend(trinput.serialize())
		if not skipOutputLocktime:
			writeVarint(len(self.outputs), result)
			for troutput in self.outputs:
				result.extend(troutput.serialize())
			if useWitness:
				result.extend(self.witnessScript)
			result.extend(self.lockTime)
		if self.version != int_to_hex(int(1), 4):
			result.extend(self.serviceHash)
		return result
