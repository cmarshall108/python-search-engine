import logging

import tornado
from tornado.options import define, options

from engine.server import Application

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

def main():
    tornado.options.parse_command_line()
    
    app = Application()
    app.listen(options.port)
    
    logging.info(f"Search engine started on port {options.port}")
    logging.info("Press Ctrl+C to stop")
    tornado.ioloop.IOLoop.current().start()

if __name__ == "__main__":
    main()