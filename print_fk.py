<<<<<<< HEAD
from run import app, db
from sqlalchemy import inspect

with app.app_context():
    insp = inspect(db.engine)
    fks = insp.get_foreign_keys('walkin_reservations')
    print('walkin_reservations foreign keys:')
    for fk in fks:
        print(fk)
=======
from run import app, db
from sqlalchemy import inspect

with app.app_context():
    insp = inspect(db.engine)
    fks = insp.get_foreign_keys('walkin_reservations')
    print('walkin_reservations foreign keys:')
    for fk in fks:
        print(fk)
>>>>>>> 7e874df2e435e64909f80e327d94360118425f97
