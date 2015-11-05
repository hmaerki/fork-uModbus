try:
    from socketserver import TCPServer, BaseRequestHandler
except ImportError:
    from SocketServer import TCPServer, BaseRequestHandler
from binascii import hexlify

from modbus import log
from modbus.route import Map
from modbus.functions import function_factory
from modbus.utils import unpack_mbap, pack_mbap


def get_server(host, port):
    """ Return :class:`modbus.Server` bound to given port and listening for
    given host.  :class:`modbus.RequestHandler` is passed as
    RequestHandlerClass.

        >>> server = get_server('localhost', 502)
        >>> server serve_forever()

    :param host: Hostname.
    :param port: Port number.
    :return: Server, subclass of socketserver.TCPServer.
    """
    return Server((host, port), RequestHandler)


class Server(TCPServer):
    """ A subclass of :class:`socketserver.TCPServer`.  """
    def __init__(self, server_address, RequestHandlerClass):
        TCPServer.__init__(self, server_address, RequestHandlerClass)
        self.route_map = Map()

    def route(self, slave_ids=None, function_codes=None, addresses=None):
        """ A decorator that is used to register an endpoint for a given
        rule::

            @server.route(slave_ids=[1], function_codes=[1, 2], addresses=list(range(100, 200)))
            def read_single_bit_values(slave_id, address):
                return random.choise([0, 1])

        :param slave_ids: A list or set with slave id's.
        :param function_codes: A list or set with function codes.
        :param addresses: A list or set with addresses.
        """
        def inner(f):
            self.route_map.add_rule(f, slave_ids, function_codes, addresses)
            return f

        return inner


class RequestHandler(BaseRequestHandler):
    """ A subclass of :class:`socketserver.BaseRequestHandler` dispatching
    incoming Modbus TCP/IP request using the server's :attr:`route_map`.

    """
    def handle(self):
        request_adu = self.request.recv(1024).strip()
        log.info('<-- {0} - {1}.'.format(self.client_address[0],
                 hexlify(request_adu)))
        transaction_id, protocol_id, _, unit_id = unpack_mbap(request_adu[:7])

        function = function_factory(request_adu[7:])
        results = function.execute(unit_id, self.server.route_map)

        try:
            # ReadFunction's use results of callbacks to build response PDU...
            response_pdu = function.create_response_pdu(results)
        except TypeError:
            # ...other functions don't.
            response_pdu = function.create_response_pdu()

        response_mbap = pack_mbap(transaction_id, protocol_id,
                                  len(response_pdu) + 1, unit_id)

        response_adu = response_mbap + response_pdu
        log.info('--> {0} - {1}.'.format(self.client_address[0],
                 hexlify(response_adu)))
        self.request.sendall(response_mbap + response_pdu)