from btchip.btchip import btchip
from btchip.bitcoinTransaction import bitcoinTransaction, bitcoinInput, bitcoinOutput
from btchip.bitcoinVarint import *
from btchip.btchipHelpers import parse_bip32_path

class eccoinTransaction(bitcoinTransaction):
    def __init__(self, data=None):
        self.version = ""
        self.timestamp = ""
        self.inputs = []
        self.outputs = []
        self.lockTime = ""
        self.witness = False
        self.witnessScript = ""
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
            else:
                self.lockTime = data[offset:offset + 4]

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
        return result

    def __str__(self):
        buf =  "Version : " + hexlify(self.version) + "\r\n"
        buf =  "Timestamp : " + hexlify(self.timestamp) + "\r\n"
        index = 1
        for trinput in self.inputs:
            buf += "Input #" + str(index) + "\r\n"
            buf += str(trinput)
            index+=1
        index = 1
        for troutput in self.outputs:
            buf += "Output #" + str(index) + "\r\n"
            buf += str(troutput)
            index+=1
        buf += "Locktime : " + hexlify(self.lockTime) + "\r\n"
        if self.witness:
            buf += "Witness script : " + hexlify(self.witnessScript) + "\r\n"
        return buf

class btchip_eccoin(btchip):
    def __init__(self, dongle):
        btchip.__init__(self, dongle)

    # change to original btchip: version field is followed by a timestamp field
    def getTrustedInput(self, transaction, index):
        result = {}
        # Header
        apdu = [ self.BTCHIP_CLA, self.BTCHIP_INS_GET_TRUSTED_INPUT, 0x00, 0x00 ]
        params = bytearray.fromhex("%.8x" % (index))
        params.extend(transaction.version)
        params.extend(transaction.timestamp)
        writeVarint(len(transaction.inputs), params)
        apdu.append(len(params))
        apdu.extend(params)
        self.dongle.exchange(bytearray(apdu))
        # Each input
        for trinput in transaction.inputs:
            apdu = [ self.BTCHIP_CLA, self.BTCHIP_INS_GET_TRUSTED_INPUT, 0x80, 0x00 ]
            params = bytearray(trinput.prevOut)
            writeVarint(len(trinput.script), params)
            apdu.append(len(params))
            apdu.extend(params)
            self.dongle.exchange(bytearray(apdu))
            offset = 0
            while True:
                blockLength = 251
                if ((offset + blockLength) < len(trinput.script)):
                    dataLength = blockLength
                else:
                    dataLength = len(trinput.script) - offset
                params = bytearray(trinput.script[offset : offset + dataLength])
                if ((offset + dataLength) == len(trinput.script)):
                    params.extend(trinput.sequence)
                apdu = [ self.BTCHIP_CLA, self.BTCHIP_INS_GET_TRUSTED_INPUT, 0x80, 0x00, len(params) ]
                apdu.extend(params)
                self.dongle.exchange(bytearray(apdu))
                offset += dataLength
                if (offset >= len(trinput.script)):
                    break
        # Number of outputs
        apdu = [ self.BTCHIP_CLA, self.BTCHIP_INS_GET_TRUSTED_INPUT, 0x80, 0x00 ]
        params = []
        writeVarint(len(transaction.outputs), params)
        apdu.append(len(params))
        apdu.extend(params)
        self.dongle.exchange(bytearray(apdu))
        # Each output
        indexOutput = 0
        for troutput in transaction.outputs:
            apdu = [ self.BTCHIP_CLA, self.BTCHIP_INS_GET_TRUSTED_INPUT, 0x80, 0x00 ]
            params = bytearray(troutput.amount)
            writeVarint(len(troutput.script), params)
            apdu.append(len(params))
            apdu.extend(params)
            self.dongle.exchange(bytearray(apdu))
            offset = 0
            while (offset < len(troutput.script)):
                blockLength = 255
                if ((offset + blockLength) < len(troutput.script)):
                    dataLength = blockLength
                else:
                    dataLength = len(troutput.script) - offset
                apdu = [ self.BTCHIP_CLA, self.BTCHIP_INS_GET_TRUSTED_INPUT, 0x80, 0x00, dataLength ]
                apdu.extend(troutput.script[offset : offset + dataLength])
                self.dongle.exchange(bytearray(apdu))
                offset += dataLength
        # Locktime
        apdu = [ self.BTCHIP_CLA, self.BTCHIP_INS_GET_TRUSTED_INPUT, 0x80, 0x00, len(transaction.lockTime) ]
        apdu.extend(transaction.lockTime)
        response = self.dongle.exchange(bytearray(apdu))
        result['trustedInput'] = True
        result['value'] = response
        return result

    # change to original btchip: version field is followed by a timestamp field
    def startUntrustedTransaction(self, newTransaction, inputIndex, outputList, redeemScript, version, timestamp, cashAddr=False, continueSegwit=False):
        # Start building a fake transaction with the passed inputs
        segwit = False
        if newTransaction:
            for passedOutput in outputList:
                if ('witness' in passedOutput) and passedOutput['witness']:
                    segwit = True
                    break
        if newTransaction:
            if segwit:
                p2 = 0x03 if cashAddr else 0x02
            else:
                p2 = 0x00
        else:
                p2 = 0x10 if continueSegwit else 0x80
        apdu = [ self.BTCHIP_CLA, self.BTCHIP_INS_HASH_INPUT_START, 0x00, p2 ]
        params = bytearray(version.to_bytes(4, byteorder="little"))
        params += timestamp.to_bytes(4, byteorder="little")
        writeVarint(len(outputList), params)
        apdu.append(len(params))
        apdu.extend(params)
        self.dongle.exchange(bytearray(apdu))
        # Loop for each input
        currentIndex = 0
        for passedOutput in outputList:
            if ('sequence' in passedOutput) and passedOutput['sequence']:
                sequence = bytearray.fromhex(passedOutput['sequence'])
            else:
                sequence = bytearray([0xFF, 0xFF, 0xFF, 0xFF]) # default sequence
            apdu = [ self.BTCHIP_CLA, self.BTCHIP_INS_HASH_INPUT_START, 0x80, 0x00 ]
            params = []
            script = bytearray(redeemScript)
            if ('trustedInput' in passedOutput) and passedOutput['trustedInput']:
                params.append(0x01)
            elif ('witness' in passedOutput) and passedOutput['witness']:
                params.append(0x02)
            else:
                params.append(0x00)
            if ('trustedInput' in passedOutput) and passedOutput['trustedInput']:
                params.append(len(passedOutput['value']))
            params.extend(passedOutput['value'])
            if currentIndex != inputIndex:
                script = bytearray()
            writeVarint(len(script), params)
            apdu.append(len(params))
            apdu.extend(params)
            self.dongle.exchange(bytearray(apdu))
            offset = 0
            while(offset < len(script)):
                blockLength = 255
                if ((offset + blockLength) < len(script)):
                    dataLength = blockLength
                else:
                    dataLength = len(script) - offset
                params = script[offset : offset + dataLength]
                if ((offset + dataLength) == len(script)):
                    params.extend(sequence)
                apdu = [ self.BTCHIP_CLA, self.BTCHIP_INS_HASH_INPUT_START, 0x80, 0x00, len(params) ]
                apdu.extend(params)
                self.dongle.exchange(bytearray(apdu))
                offset += blockLength
            if len(script) == 0:
                apdu = [ self.BTCHIP_CLA, self.BTCHIP_INS_HASH_INPUT_START, 0x80, 0x00, len(sequence) ]
                apdu.extend(sequence)
                self.dongle.exchange(bytearray(apdu))
            currentIndex += 1

    # use eccoinTransaction class instead btchip provided bitcoinTransaction
    def finalizeInput(self, outputAddress, amount, fees, changePath, rawTx=None):
        alternateEncoding = False
        donglePath = parse_bip32_path(changePath)
        if self.needKeyCache:
            self.resolvePublicKeysInPath(changePath)
        result = {}
        outputs = None
        if rawTx is not None:
            try:
                fullTx = eccoinTransaction(bytearray(rawTx))
                outputs = fullTx.serializeOutputs()
                if len(donglePath) != 0:
                    apdu = [ self.BTCHIP_CLA, self.BTCHIP_INS_HASH_INPUT_FINALIZE_FULL, 0xFF, 0x00 ]
                    params = []
                    params.extend(donglePath)
                    apdu.append(len(params))
                    apdu.extend(params)
                    response = self.dongle.exchange(bytearray(apdu))
                offset = 0
                while (offset < len(outputs)):
                    blockLength = self.scriptBlockLength
                    if ((offset + blockLength) < len(outputs)):
                        dataLength = blockLength
                        p1 = 0x00
                    else:
                        dataLength = len(outputs) - offset
                        p1 = 0x80
                    apdu = [ self.BTCHIP_CLA, self.BTCHIP_INS_HASH_INPUT_FINALIZE_FULL, \
                        p1, 0x00, dataLength ]
                    apdu.extend(outputs[offset : offset + dataLength])
                    response = self.dongle.exchange(bytearray(apdu))
                    offset += dataLength
                alternateEncoding = True
            except Exception as e:
                print(e)
                pass
        if not alternateEncoding:
            print('alternateEncoding: ' + str(alternateEncoding))
            apdu = [ self.BTCHIP_CLA, self.BTCHIP_INS_HASH_INPUT_FINALIZE, 0x02, 0x00 ]
            params = []
            params.append(len(outputAddress))
            params.extend(bytearray(outputAddress))
            writeHexAmountBE(btc_to_satoshi(str(amount)), params)
            writeHexAmountBE(btc_to_satoshi(str(fees)), params)
            params.extend(donglePath)
            apdu.append(len(params))
            apdu.extend(params)
            response = self.dongle.exchange(bytearray(apdu))
        result['confirmationNeeded'] = response[1 + response[0]] != 0x00
        result['confirmationType'] = response[1 + response[0]]
        if result['confirmationType'] == 0x02:
            result['keycardData'] = response[1 + response[0] + 1:]
        if result['confirmationType'] == 0x03:
            offset = 1 + response[0] + 1
            keycardDataLength = response[offset]
            offset = offset + 1
            result['keycardData'] = response[offset : offset + keycardDataLength]
            offset = offset + keycardDataLength
            result['secureScreenData'] = response[offset:]
        if result['confirmationType'] == 0x04:
            offset = 1 + response[0] + 1
            keycardDataLength = response[offset]
            result['keycardData'] = response[offset + 1 : offset + 1 + keycardDataLength]
        if outputs == None:
            result['outputData'] = response[1 : 1 + response[0]]
        else:
            result['outputData'] = outputs
        return result
