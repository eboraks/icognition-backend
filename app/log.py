import logging



def get_logger(name: str = __name__) -> logging.Logger:
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG)
    console_handler.setFormatter(logging.Formatter('%(asctime)s,%(msecs)d %(name)s %(levelname)s %(message)s [%(filename)s:%(lineno)d]', datefmt='%H:%M:%S'))
    logging.getLogger().addHandler(console_handler)

    return logging.getLogger(name)