# script.py

#def get_value():
#    return "Hello, world!"
#value = get_value()
#print(value)
# script.py

import json

def get_value():
    return json.dumps("Hello, big world!")
value = get_value()
print(value)