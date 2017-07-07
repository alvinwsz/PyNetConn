#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Date    : 2016-10-25 16:31:38
# @Author  : alvin (10984438@qq.com)
# @Link    : http://www.openams.cn/
# @Version : $Id$

import os

from kivy.clock import Clock
from kivy.support import install_twisted_reactor
install_twisted_reactor()

from twisted.internet import reactor, protocol

import json
import re
import datetime
import threading
from functools import partial

class NetProtocol(protocol.Protocol):
    _data = ""
    _size = 0
    def connectionMade(self):
        self.factory.app.onConnect(self.transport)

    def connectionLost(self, reason):
        pass

    def dataReceived(self, data):
        self.factory.app.onReceive(data)


class NetFactory(protocol.ClientFactory):
    protocol = NetProtocol
    
    def __init__(self, app):
        self.app = app

    def clientConnectionLost(self, conn, reason):
        print "clientConnectionLost: ", conn, reason
        self.app.onClose(reason)

    def clientConnectionFailed(self, conn, reason):
        print "clientConnectionFailed: ", conn, reason
        self.app.handler.onConnectionFailed(self.app, reason)

class Queue():  
    def __init__(self):  
        self.queue = []

    def reset(self):
        self.queue = []

    def empty(self):  
        return self.queue == []  
    def enqueue(self,data):  
        self.queue.append(data)  
    def dequeue(self):  
        if self.empty():  
            return None  
        else:  
            return self.queue.pop(0)  
    def head(self):  
        if self.empty():  
            return None  
        else:  
            return self.queue[0]  
    def length(self):  
        return len(self.queue)  

class NetConn:
    '''
    '''
    __tx_map = {}
    tx_timeout = 0
    __timer = None
    hb_event = None
    hb_packet = None
    hb_timeout = 0
    rx_queue = None
    rx_event = None
    closing = False
    conn = None

    def __init__(self, proto):
        #assert(ITQClient.implementedBy(handler))
        self.proto = proto
        self.rx_queue = Queue()

    def connect(self, addr, handler, timeout = 60):
        self.handler = handler
        self.tx_timeout = timeout
        self.__addr = addr
        (host, port) = addr.split(':')
        print "===connect: ", host, port
        reactor.connectTCP(host, int(port), NetFactory(self))

    def isConnected(self):
        return True if self.conn else False

    def onConnect(self, transport):
        print "==onConnect", transport
        self.conn = transport
        self.handler.onConnect()

    def onClose(self, reason):
        print "onClose"
        if not self.closing:
            self.close()
            self.handler.onConnectionLost(reason)

    def close(self):
        ''' close and exit '''
        print "close"
        self.closing = True
        self.rx_queue.reset()
        for k, v in self.__tx_map.items():
            #print '%s:%s' % (k, v)
            v[1].cancel()
            self.__txTimeout(v[0])
        if self.conn:
            self.conn.loseConnection()
            del self.conn
            self.conn = None
        if self.hb_event:
            self.hb_event.cancel()
            self.hb_event = None
        if self.rx_event:
            self.rx_event.cancel()
            self.rx_event = None
        self._data = ""
        self._size = 0
 
    def reconnect(self):
        """
        """

    def tx_del(self, id):
        """
        delete the tx package waiting for response
        """
        if not self.__tx_map.has_key(id):
            return
        p = self.__tx_map[id]
        if p and p[1]:
            p[1].cancel()
        del self.__tx_map[id]

    def __txTimeout(self, p):
        print "__txTimeout: ", p
        self.__tx_map[p.pid()][1] = None
        self.tx_del(p.pid())
        #Clock.schedule_once(lambda x: self.handler.onReqTimeout(self, c))
        self.handler.onTxTimeout(self, p)

    def send(self, p, timeout=0):
        print "==========send: ", self.conn, type(p), p.string()
        #assert(IPacket.implementedBy(p))
        assert(IPacket.providedBy(p))
        #assert(isinstance(p, IPacket))
        if self.conn:
            if timeout:
                event = Clock.schedule_once(lambda x: self.__txTimeout(p), timeout)
                self.__tx_map[p.pid()] = (p, event)
            self.conn.write(p.data())

    def __rxHandler(self):
        p = self.rx_queue.dequeue()
        #print "__rxHandler", p
        if p:
            self.handler.onReceive(p)
        if self.rx_queue.empty():
            self.rx_event = None
        else:
            self.rx_event = Clock.schedule_once(lambda x: self.__rxHandler())

    def onReceive(self, data):
        p = self.proto.onReceive(data)
        if p is None:
            print "hahahah"
            return
        print "protocol.onReceive: "+p.string()
        self.rx_queue.enqueue(p)
        if self.rx_event is None:
            self.rx_event = Clock.schedule_once(lambda x: self.__rxHandler())

    def heartbeat(self, tm):
        """
        send heartbeat package, if tm==0, stop hearbeat
        """

        print '------------heartbeat: ', self.hb_event, tm
        if self.hb_event:
            self.hb_event.cancel()
            self.hb_event = None
        self.hb_timeout = tm
        if tm != 0: 
            self.__onHeartbeatTimeout()

    def __onHeartbeatTimeout(self):
        p = self.proto.pack_heartbeat()
        if self.conn and p:
            self.conn.write(p.data())
            self.hb_event = Clock.schedule_once(lambda x: self.__onHeartbeatTimeout(), self.hb_timeout)


from zope.interface import Interface  
#from zope.interface import implementer  

class IPacket(Interface):

    def data():
        """
        return formatted binary data of this package
        """
    def string():
        """format binary data into string"""
    def pid():
        """
        return id of this package
        """

class IUserProtocol(Interface): 
    def default_cfg():
        """
        return default config data for this protocol
        """
    def pack_heartbeat():
        """
        encode and return heartbeat package 
        """
    def onReceive(data): # 可以不用self
        """
        receive and parse data, return a complete package(IPacket)
        """ 

class IUserProtocolHandler(Interface): 
    def onConnectionFailed(reason):
        """

        """
    def onConnect(): # 可以不用self
        """
        Notify connected. here you can send first packet to the server
        """ 
    def onConnectionLost(reason):
        """
        
        """

    def onReceive(p):
        """
        Receive packet from server
        """

    def onTxTimeout(p):
        """
        package sent and no ack received until timeout expired
        """