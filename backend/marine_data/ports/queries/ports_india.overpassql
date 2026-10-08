[out:json][timeout:180];

area
  ["ISO3166-1"="IN"]
  ["admin_level"="2"]
  ->.india;

(
  nwr["harbour"="yes"](area.india);
  nwr["industrial"="port"](area.india);
  nwr["seamark:type"="harbour"](area.india);
  nwr["seamark:harbour:category"="port"](area.india);
  nwr["seamark:harbour:category"="fishing_harbour"](area.india);
  nwr["seamark:type"="harbour_basin"](area.india);
  nwr["amenity"="ferry_terminal"](area.india);
  nwr["seamark:type"="harbour_facility"](area.india);
  nwr["man_made"="pier"](area.india);
  nwr["leisure"="marina"](area.india);
);

out center tags;