from googlemaps import Client
from flask_googlemaps import GoogleMaps
from flask import Flask, render_template, request, jsonify, abort, redirect, flash
from google.cloud import datastore
from datetime import datetime
import requests
import yaml

app = Flask(__name__)
app.secret_key = 'newevent'

maps_config = yaml.load(open("googlemaps.yaml"))
GOOGLEMAPS_KEY = maps_config['GOOGLEMAPS_KEY']

GoogleMaps(app, key=GOOGLEMAPS_KEY)

def create_client(project_id):
    return datastore.Client(project_id)

global_client = create_client('myplace-224901')
gmaps = Client(key=GOOGLEMAPS_KEY)
latitude = None
longitude = None

def add_event(client, title, description, date, time, address):
	key = client.key('Event')

	event = datastore.Entity(key=key)
	event['title'] = title
	event['description'] = description
	event['date'] = date
	event['time'] = time

	geocode_result = gmaps.geocode(address)
	if len(geocode_result) > 0:
		location = geocode_result[0]['geometry']['location']
		event['latitude'] = location['lat']
		event['longitude'] = location['lng']

	client.put(event)

	return event.key

def delete_event(client, event_id):
    key = client.key('Event', event_id)
    client.delete(key)

def list_events(client, my_lat, my_lng):
	query = client.query(kind='Event')

	event_list = []
	index = 1
	now = datetime.now()
	for event in list(query.fetch()):
		new_event = {}
		new_event['title'] = event['title']
		new_event['description'] = event['description']
		new_event['date'] = event['date']
		new_event['time'] = event['time']
		new_event['latitude'] = event['latitude']
		new_event['longitude'] = event['longitude']
		new_event['id'] = "map" + str(event.id)

		distance_bus = gmaps.distance_matrix(origins=(my_lat, my_lng), 
										 destinations=(event['latitude'], event['longitude']),
										 units='metrics',
										 mode='transit',
										 transit_mode='bus',
                                     	 departure_time=now)

		if distance_bus['status'] == 'OK':
			for row in distance_bus['rows']:
				for element in row['elements']:
					if element['status'] == 'OK':
						new_event['distance_bus'] = element['distance']['text']
						new_event['duration_bus'] = element['duration']['text']

		distance_driving = gmaps.distance_matrix(origins=(my_lat, my_lng), 
										 destinations=(event['latitude'], event['longitude']),
										 units='metrics',
										 mode='driving',
                                     	 departure_time=now)

		if distance_driving['status'] == 'OK':
			for row in distance_driving['rows']:
				for element in row['elements']:
					if element['status'] == 'OK':
						new_event['distance_driving'] = element['distance']['text']
						new_event['duration_driving'] = element['duration']['text']

		body = {}
		body['service-name'] = 'current weather'
		body['client-appspot'] = 'myplace-224901'
		body['server-appspot'] = 'world-weather-watch'

		response = requests.post('https://orchestrator-224010.appspot.com/token/create', json=body)

		if response.status_code == requests.codes.ok:
			response_json = response.json()
			response = requests.get('https://world-weather-watch.appspot.com/weather/current?lat=' + str(event['latitude']) + "&lng=" + str(event['longitude']) + "&token-id=" + response_json['token-id'] + "&client-appspot=myplace-224901")
			if response.status_code == requests.codes.ok:
				response_json = response.json()
				new_event['temperature'] = response_json['temp-c']
				new_event['img'] = response_json['weather-icon']
		
		index += 1
		event_list.append(new_event)

	return event_list

@app.route('/')
def home():

	global latitude
	global longitude

	if latitude == None or longitude == None:
		latitude = request.args.get('latitude')
		longitude = request.args.get('longitude')
	
	if latitude == None or longitude == None:
		return render_template('index.html')
	else:
		return render_template('home.html', events=list_events(global_client, latitude, longitude))

@app.route('/event', methods = ['POST'])
def event():
	global global_client

	result = request.get_json()

	title = result['title']
	description = result['description']
	date = result['date']
	time = result['time']
	address = result['address']
	token = result['token-id']
	project_id = result['client-appspot']

	if title == None or description == None or date == None or time == None or address == None or token == None or project_id == None:
		abort(400)
	else:

		body = {}
		body['token-id'] = token
		body['server-appspot'] = 'myplace-224901'
		body['client-appspot'] = project_id
		body['service-name'] = 'Register event'

		response = requests.post('https://orchestrator-224010.appspot.com/token/validate', json=body)

		if response.status_code == requests.codes.ok:
			event = add_event(global_client, title, description, date, time, address)
			obj = {}
			obj['id'] = event.id
			return jsonify(({'event': obj}))
		else:
			abort(400)

@app.route('/events')
def events():
	global global_client

	event_id = request.args.get('id')
	token = request.args.get('token-id')
	project_id = request.args.get('client-appspot')

	if token == None or project_id == None:
		abort(400)

	body = {}
	body['token-id'] = token
	body['server-appspot'] = 'myplace-224901'
	body['client-appspot'] = project_id
	body['service-name'] = 'List events'

	response = requests.post('https://orchestrator-224010.appspot.com/token/validate', json=body)

	if response.status_code == requests.codes.ok:
		query = global_client.query(kind='Event')
		event_list = []
		for event in list(query.fetch()):
			obj = {}
			obj['id'] = event.id
			obj['title'] = event['title']
			obj['description'] = event['description']
			obj['date'] = event['date']
			obj['time'] = event['time']
			obj['latitude'] = event['latitude']
			obj['longitude'] = event['longitude']

			if event_id != None and str(event_id) == str(event.id):
				return jsonify(({'event': obj}))
			elif event_id == None:
				event_list.append(obj)
		if len(event_list) == 0 and event_id != None:
			abort(404)
		else:
			return jsonify(({'events': event_list}))
	else:
		abort(400)

@app.route('/newevent',methods = ['POST', 'GET'])
def newevent():
	if request.method == 'GET':
		return render_template('newevent.html')
	elif request.method == 'POST':
		result = request.form
		title = result['title']
		description = result['description']
		date = result['date']
		time = result['time']
		address = result['address']
		add_event(global_client, title, description, date, time, address)
		flash('Event created!')
		return redirect(request.path,code=302)
		#return render_template('home.html', events=list_events(global_client, latitude, longitude))

if __name__ == '__main__':
	app.run(debug=True, host='0.0.0.0', port=8080)