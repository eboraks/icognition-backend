import logging



def get_logger(name: str = __name__) -> logging.Logger:
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s,%(msecs)d %(name)s %(levelname)s %(message)s [%(filename)s:%(lineno)d]',
        datefmt='%H:%M:%S'
    )
    return logging.getLogger(name)