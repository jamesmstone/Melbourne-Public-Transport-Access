import hmac
import requests
import csv
import itertools
import base64
import hashlib
import os
import time
from math import cos, sin, radians, degrees, asin, atan2, sqrt
from urllib.request import *
from urllib.parse import *

# p12 password notasecret
 
PATH_TO_KEY = './'
SECRET_CLIENT = '5qYJDeYBBbbIeanFMXd2DHVi'
TRY_ATTEMPT_MAX = 5
GROUP_N = 50
SLEEP_DELAY = 0.5  # 1000 per 10 seconds; 100 per second; 50 per 0.5 seconds
 
 
def mygrouper(n, iterable):
    """
    Cut a list into chunks of (n)
    """
    args = [iter(iterable)] * n
    return ([e for e in t if e is not None] for t in itertools.zip_longest(*args))
 
 
def geocode_address(private_key, address):
    """
    Geocode address into latitude and longitudes (5 dp)
    """
    if address == '':
        raise Exception('address cannot be blank.')
    elif isinstance(address, str):
        # URL safe
        address_str = quote(address)
    else:
        raise Exception('address should be a string.')
 
    prefix = 'https://maps.googleapis.com/maps/api/geocode/json'
    url = urlparse('{0}?address={1}&client={2}'.format(prefix,
                                                       address_str,
                                                       SECRET_CLIENT))
    url_to_sign = url.path + "?" + url.query
    decoded_key = base64.urlsafe_b64decode(private_key)
    signature = hmac.new(decoded_key, url_to_sign.encode(), hashlib.sha1)
    encoded_signature = base64.urlsafe_b64encode(signature.digest())
    original_url = url.scheme + '://' + url.netloc + url.path + '?' + url.query
    full_url = original_url + '&signature=' + encoded_signature.decode()
 
    # Request geocode from address
    d = requests.get(full_url).json()
    if not d['status'] == 'OK':
        raise Exception('Error. Google Maps API return status: {}'.format(d['status']))
    # Accuracy: 5 Decimal Places: 1.11metres
    geocode = ['%.5f' % d['results'][0]['geometry']['location']['lat'],
               '%.5f' % d['results'][0]['geometry']['location']['lng']]
    # print('Geocoding of %s successful: %s' % (address, geocode))
    print(full_url)
    return geocode
 
 
def select_destination(origin_geocode,
                       angle,
                       radius):
    """
    Given a centre, radius, and bearing find the end-point
    """
    r = 3959  # Radius of the Earth in miles
    bearing = radians(angle)  # Bearing in radians converted from angle in degrees
    lat1 = radians(float(origin_geocode[0]))
    lng1 = radians(float(origin_geocode[1]))
    lat2 = asin(sin(lat1) * cos(radius / r) + cos(lat1) * sin(radius / r) * cos(bearing))
    lng2 = lng1 + atan2(sin(bearing) * sin(radius / r) * cos(lat1), cos(radius / r) - sin(lat1) * sin(lat2))
    lat2 = degrees(lat2)
    lng2 = degrees(lng2)
    # Check distances (miles)
    # print(haversine(origin_geocode,['%.5f' % lat2, '%.5f' % lng2]))
    # 5 Decimal Places: 1.11metres
    return ['%.5f' % lat2, '%.5f' % lng2]
 
 
def haversine(origin,
              destination):
    """
    Find distance between a pair of lat/lng coordinates
    """
    # Accept only latitude/longitude coordinates
    if (isinstance(origin, list) and len(origin) == 2) and \
            (isinstance(destination, list) and len(destination) == 2):
        # convert decimal degrees to radians
        lat1, lon1, lat2, lon2 = map(radians, [float(origin[0]), float(origin[1]),
                                               float(destination[0]), float(destination[1])])
        # Haversines
        dlon = lon2 - lon1
        dlat = lat2 - lat1
        a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
        c = 2 * asin(sqrt(a))
        r = 3959
        # Miles
        return '%.2f' % (c * r)
 
 
def build_url(private_key,
              mode_using,
              origin,
              destination):
    """
    Create URL to send to Google API given origin and destination
    """
    if destination == '':
        raise Exception('destination cannot be blank.')
    elif isinstance(destination, str):
        destination_str = quote(destination)
    elif isinstance(destination, list):
        destination_str = ''
        for element in destination:
            if isinstance(element, str):
                destination_str = '{0}|{1}'.format(destination_str, quote(element))
            elif isinstance(element, list) and len(element) == 2:
                destination_str = '{0}|{1}'.format(destination_str, ','.join(map(str, element)))
            else:
                raise Exception('destination must be a list of lists [lat, lng] or a list of strings.')
        destination_str = destination_str.strip('|')
    else:
        raise Exception('destination must be a a list of lists [lat, lng] or a list of strings.')
    # '|' not correctly handled so use '%7C' instead
    destination_str = destination_str.replace('|', '%7C')
 
    # print('Building URL...')
    prefix = 'https://maps.googleapis.com/maps/api/distancematrix/json?mode=%s' % mode_using
    origin_str = ','.join(map(str, origin))
    url = urlparse('{0}&origins={1}&destinations={2}&client={3}'.format(prefix,
                                                                        origin_str,
                                                                        destination_str,
                                                                        SECRET_CLIENT))
    url_to_sign = url.path + "?" + url.query
    decoded_key = base64.urlsafe_b64decode(private_key)
    signature = hmac.new(decoded_key, url_to_sign.encode(), hashlib.sha1)
    encoded_signature = base64.urlsafe_b64encode(signature.digest())
    original_url = url.scheme + '://' + url.netloc + url.path + '?' + url.query
    full_url = original_url + '&signature=' + encoded_signature.decode()
    return full_url
 
 
def parse_json(url):
    """
    Extract data from Google returned json
    """
    response = requests.get(url)
    d = response.json()
    # print('Parsing JSON - Status: %s' % d['status'])
    if not d['status'] == 'OK':
        raise Exception('Error. Google Maps API return status: {}'.format(d['status']))
    addresses = d['destination_addresses']
 
    i = 0
    durations = [0] * len(addresses)
    for row in d['rows'][0]['elements']:
        if not row['status'] == 'OK':
            durations[i] = 9999
        else:
            durations[i] = row['duration']['value'] / 60
        i += 1
    return [addresses, durations]
 
 
def html_isochrone(coord_set,
                   radius_km,
                   map_name):
    """
    Create a JS map of the isochrones
    """
    htmltext = """<!DOCTYPE html >
      <style type="text/css">
                html, body {
                    height: 100%;
                    width: 100%;
                    padding: 0px;
                    margin: 0px;
                }
    </style>
    <head>
    <meta name="viewport" content="initial-scale=1.0, user-scalable=no" />
    <meta http-equiv="content-type" content="text/html; charset=UTF-8"/>
    <title>Isochrone Analysis</title>
    <xml id="myxml">
    <markers>
    """
    for coord in coord_set:
        print(coord)
        rowcord = '<marker name = "' + coord[2] + '" lat = "' + coord[0] + '" lng = "' + coord[1] + '"/>\n'
        htmltext += rowcord
    htmltext += """
    </markers>
    </xml>
    <script type="text/javascript" src="https://maps.googleapis.com/maps/api/js?&sensor=false&libraries=geometry"></script>
    <script type="text/javascript">
    var XML = document.getElementById("myxml");
    if(XML.documentElement == null)
    XML.documentElement = XML.firstChild;
    var MARKERS = XML.getElementsByTagName("marker");
    """
    htmltext += "var RADIUS_KM = " + str(radius_km) + ";"
    htmltext += """
    var map;
    var geocoder = new google.maps.Geocoder();
    var BUFFER = 1.1;
    var circles_transit = [];
    var circles_driving = [];
    var circles_walking = [];
    function drawCircle(point, radius, dir){
        // Function from stackoverflow
        var d2r = Math.PI / 180;   // degrees to radians
        var r2d = 180 / Math.PI;   // radians to degrees
        var earthsradius = 3963; // 3963 is the radius of the earth in miles
        var points = 32;
        // find the radius in lat/lon
        var rlat = (radius / earthsradius) * r2d;
        var rlng = rlat / Math.cos(point.lat() * d2r);
 
        var extp = new Array();
        if (dir==1) {var start=0;var end=points+1} // one extra here makes sure we connect the
        else{var start=points+1;var end=0}
        for (var i=start; (dir==1 ? i < end : i > end); i=i+dir)
        {
            var theta = Math.PI * (i / (points/2));
            ey = point.lng() + (rlng * Math.cos(theta)); // center a + radius x * cos(theta)
            ex = point.lat() + (rlat * Math.sin(theta)); // center b + radius y * sin(theta)
            extp.push(new google.maps.LatLng(ex, ey));
        }
        return extp;
    }"""
    htmltext += """
    function load() {
        // Initialize around City, London
        var my_lat = 51.518175;
        var my_lng = -0.129064;
        // Custom formatting
        var mapOptions = {
                center: new google.maps.LatLng(my_lat, my_lng),
                zoom: 12,
                styles: [
                {"featureType": "administrative","stylers":[{ "saturation":-80},{"visibility":"on"}]},
                {"featureType":"landscape.man_made","elementType":"geometry","stylers":[{"color":"#f7f1df"}]},
                {"featureType":"landscape.natural","elementType":"geometry","stylers":[{"color":"#d0e3b4"}]},
                {"featureType":"landscape.natural.terrain","elementType":"geometry","stylers":[{"visibility":"on"}]},
                {"featureType":"poi","elementType":"labels","stylers":[{"visibility":"off"}]},
                {"featureType":"poi.business","elementType":"all","stylers":[{"visibility":"off"}]},
                {"featureType":"poi.medical","elementType":"geometry","stylers":[{"color":"#fbd3da"}]},
                {"featureType":"poi.park","elementType":"geometry","stylers":[{"color":"#bde6ab"}]},
                {"featureType":"road","elementType":"geometry.stroke","stylers":[{"visibility":"off"}]},
                {"featureType":"road","elementType":"labels","stylers":[{"visibility":"off"}]},
                {"featureType":"road.highway","elementType":"geometry.fill","stylers":[{"color":"#ffe15f"}]},
                {"featureType":"road.highway","elementType":"geometry.stroke","stylers":[{"color":"#efd151"}]},
                {"featureType":"road.arterial","elementType":"geometry.fill","stylers":[{"color":"#ffffff"}]},
                {"featureType":"road.local","elementType":"geometry.fill","stylers":[{"color":"black"}]},
                {"featureType":"transit.station.airport","elementType":"geometry.fill","stylers":[{"color":"#cfb2db"}]},
                {"featureType":"water","elementType":"geometry","stylers":[{"color":"#a2daf2"}]},
                {"featureType":"all", "stylers":[{"lightness":20}]}
                ]
        };
        map = new google.maps.Map(document.getElementById('map'),
            mapOptions);
        var bounds = new google.maps.LatLngBounds();
        for (var i = 0; i < MARKERS.length; i++) {
            var name = MARKERS[i].getAttribute("name");
            if (name == 'transit') {
                var point_i = new google.maps.LatLng(
                    parseFloat(MARKERS[i].getAttribute("lat")),
                    parseFloat(MARKERS[i].getAttribute("lng")));
                circles_transit.push(drawCircle(point_i,RADIUS_KM*(1000/1609.344)*BUFFER,1))
                bounds.extend(point_i);
            }
            if (name == 'driving') {
                var point_i = new google.maps.LatLng(
                    parseFloat(MARKERS[i].getAttribute("lat")),
                    parseFloat(MARKERS[i].getAttribute("lng")));
                circles_driving.push(drawCircle(point_i,RADIUS_KM*(1000/1609.344)*BUFFER,1))
                bounds.extend(point_i);
            }
            if (name == 'walking') {
                var point_i = new google.maps.LatLng(
                    parseFloat(MARKERS[i].getAttribute("lat")),
                    parseFloat(MARKERS[i].getAttribute("lng")));
                circles_walking.push(drawCircle(point_i,RADIUS_KM*(1000/1609.344)*BUFFER,1))
                bounds.extend(point_i);
            }
        };"""
    htmltext += """
        var col_transit = "{0}";
        var col_driving = "{1}";
        var col_walking = "{2}";
    """.format("green", "blue", "red")
    htmltext += """
        if (circles_transit.length > 0) {
            var joined_transit = new google.maps.Polygon({
                    paths: circles_transit,
                    strokeColor: col_transit,
                    strokeOpacity: 0.35,
                    strokeWeight: 0,
                    fillColor: col_transit,
                    fillOpacity: 0.35
            });
            joined_transit.setMap(map);
        }
        if (circles_driving.length > 0) {
            var joined_driving = new google.maps.Polygon({
                    paths: circles_driving,
                    strokeColor: col_driving,
                    strokeOpacity: 0.35,
                    strokeWeight: 0,
                    fillColor: col_driving,
                    fillOpacity: 0.35
            });
            joined_driving.setMap(map);
        }
        if (circles_walking.length > 0) {
            var joined_walking = new google.maps.Polygon({
                    paths: circles_walking,
                    strokeColor: col_walking,
                    strokeOpacity: 0.35,
                    strokeWeight: 0,
                    fillColor: col_walking,
                    fillOpacity: 0.35
            });
            joined_walking.setMap(map);
        }
        map.fitBounds(bounds);
    }
    </script>
    </head>
    <body onload="load()">
    <center>
    <div style="padding-top: 20px; padding-bottom: 20px;">
    <div id="map" style="width:90%; height:1024px;"></div>
    </center>
    </body>
    </html>
    """
    with open('%s_raw_points.html' % map_name, 'w') as f:
        f.write(htmltext)
    f.close()
 
 
def createcoordinates(origin,
                      radius_km,
                      southwest_lat,
                      southwest_lng,
                      northeast_lat,
                      northeast_lng,
                      circ_cutoff_miles=0):
    """
    Fill 2D space with circles
    """
    coords_set = []
    earth_radius_km = 6371
    lat_start = radians(southwest_lat)
    lon_start = radians(southwest_lng)
    lat = lat_start
    lon = lon_start
    lat_level = 1
    while True:
        if (degrees(lat) <= northeast_lat) & (degrees(lon) <= northeast_lng):
            coords_set.append(['%.5f' % degrees(lat), '%.5f' % degrees(lon)])
        parallel_radius = earth_radius_km * cos(lat)
        if degrees(lat) > northeast_lat:
            break
        elif degrees(lon) > northeast_lng:
            lat_level += 1
            lat += (radius_km / earth_radius_km) + (radius_km / earth_radius_km) * sin(radians(30))
            if lat_level % 2 != 0:
                lon = lon_start
            else:
                lon = lon_start + (radius_km / parallel_radius) * cos(radians(30))
        else:
            lon += 2 * (radius_km / parallel_radius) * cos(radians(30))
    # Cut the box to a circle
    if circ_cutoff_miles > 0:
        print("Carving circle with radius: %.2f miles" % circ_cutoff_miles)
        coords_set = [coord for coord in coords_set if float(haversine(origin, coord)) <= circ_cutoff_miles]
        print('Circle Coordinates-set contains %d coordinates' % len(coords_set))
    return coords_set
 
 
def setupkey(key_loc='GeocodeKeyV1.txt'):
    """
    Connect to network and read Google API password
    """
    if os.path.isfile(os.path.join(PATH_TO_KEY, key_loc)):
        key_file = open(os.path.join(PATH_TO_KEY, key_loc), 'r')
        Key_file_message = key_file.readline()
        Key_file_sleep = key_file.readline()
        print('%s' % Key_file_message)
        key = key_file.readline()
        key_file.close()
        return key
    else:
        print('Key File Not Found. Make Sure You are Connected to Network and Using latest Version of Code')
        time.sleep(10)
        exit()
 
def runsearch(duration,
              centre,
              area,
              travel_mode):
    """
    Run the isochrone search
    """
    # Initiate variables
    secret_key = setupkey(key_loc='GeocodeKeyV1.txt')
    map_coords_set = []
    end_coordinates = []
    counter = 0
 
    name = '%s_%dmin' % (centre, duration)
    produce_csv_file = name + '.csv'
    if os.path.isfile(produce_csv_file):
        raise Exception('Please delete: %s' % produce_csv_file)
    else:
        print("Producing: %s" % produce_csv_file)
 
    origin = geocode_address(secret_key, centre)
    print("Geocoded Origin: %s" % origin)
 
    # Loop through travel modes
    for mode_using in travel_mode:
        print(mode_using)
        if mode_using == "walking":
            radius_km = 0.05
            max_distance_miles = duration * (4/60)
        elif mode_using == "driving":
            radius_km = 0.1
            if area == "urban":
                max_distance_miles = duration * (20/60)
            else:
                max_distance_miles = duration * (40/60)
        elif mode_using == "transit":
            radius_km = 0.1
            max_distance_miles = duration * (20/60)
        else:
            raise Exception("Invalid travel mode")
 
        # Find bounding box
        coordinates = createcoordinates(
            origin,
            radius_km,
            float(select_destination(origin, 225, sqrt((max_distance_miles * max_distance_miles) * 2))[0]),
            float(select_destination(origin, 225, sqrt((max_distance_miles * max_distance_miles) * 2))[1]),
            float(select_destination(origin, 45, sqrt((max_distance_miles * max_distance_miles) * 2))[0]),
            float(select_destination(origin, 45, sqrt((max_distance_miles * max_distance_miles) * 2))[1]),
            max_distance_miles
        )
 
        # Plot the 'before' map:
        html_isochrone([[coord[0], coord[1], mode_using] for coord in coordinates],
                       radius_km,
                       '%s_%s_start' % (name, mode_using))
 
        # Break up coordinates into groups of 50 (process in bulk):
        group_coordinates = mygrouper(GROUP_N, coordinates)
 
        for one_coord in group_coordinates:
            # Note that the API will get the closest match by having a buffer around what
            # it considers to be the point. This is useful generally, however may mean that
            # we end up with points in the water because it has used the closest land point
            # To 'fix' this one would then geocode the points and used the returned coordinates
            url = build_url(secret_key, mode_using, origin, one_coord)
            if len(url) >= 2048:
                raise Exception('URL length %d exceeds maximum of 2048' % (len(url)))
            print(url)
 
            time.sleep(SLEEP_DELAY)
            try_count = 0
 
            while try_count < TRY_ATTEMPT_MAX:
                try:
                    data = parse_json(url)
                    break
                except Exception as err:
                    time.sleep(5)
                    print('Waiting 5 seconds ... retry: %s' % err)
                    try_count += 1
 
            if try_count == TRY_ATTEMPT_MAX:
                raise Exception('Failed to calculate distances - possibly API LIMIT REACHED')
 
            for i in range(0, len(one_coord)):
                assert len(one_coord[i]) == 2
                counter += 1
                # Save all points (latitude, longitude, minutes)
                row_append = [one_coord[i][0], one_coord[i][1], data[1][i], mode_using]
                end_coordinates.append(row_append)
                if data[1][i] <= duration:
                    print('Found point within %d minutes' % duration)
                    map_coords_set.append([one_coord[i][0], one_coord[i][1], mode_using])
 
    # OUTPUT RESULTS to CSV
    f = open(produce_csv_file, 'w', newline='')
    w = csv.writer(f)
    for endcord in end_coordinates:
        w.writerow(endcord)
    f.close()
 
    # CREATE FINAL MAP
    html_isochrone(map_coords_set, radius_km, '%s_finished' % name)
 
 
if __name__ == '__main__':
    # SETUP variables
    duration = 30  # Minutes
    centre = 'Melbourne, Australia'
    area = 'urban'
    travel_mode = ['walking', 'driving']
    # RUN
    runsearch(duration,
              centre,
              area,
              travel_mode)