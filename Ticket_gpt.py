import datetime
from dateutil.relativedelta import relativedelta


class Ticket_gpt:

  def __init__(self, ticket_no, active_date, expired_date, token_amt,
               ticket_price, lineuser_id):
    self.ticket_no = ticket_no
    self.issued_date = datetime.date.today()
    self.active_date = datetime.date.today()
    self.expired_date = datetime.date.today() + relativedelta(months=1)
    self.token_amt = token_amt
    self.ticket_price = ticket_price
    self.lineuser_id = lineuser_id
