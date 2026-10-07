// Globe viewer: draws each map's box and lists every map under the point you click.

const GEOJSON_URL = "/data/gold/map_library.geojson";
const BOX_COLOR = "#d9480f";

const map = new maplibregl.Map({
  container: "map",
  center: [-90, 44.5],
  zoom: 2,
  style: {
    version: 8,
    projection: { type: "globe" },
    sources: {
      basemap: {
        type: "raster",
        tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
        tileSize: 256,
        maxzoom: 19,
        attribution: "© OpenStreetMap contributors",
      },
    },
    layers: [{ id: "basemap", type: "raster", source: "basemap" }],
    sky: { "atmosphere-blend": 0.6 },
  },
});
map.addControl(new maplibregl.NavigationControl(), "top-right");

// Each map: its title, where the file lives, and its box as [west, south, east, north].
let maps = [];

function boxOf(feature) {
  const ring = feature.geometry.coordinates[0];
  const lons = ring.map((point) => point[0]);
  const lats = ring.map((point) => point[1]);
  return [Math.min(...lons), Math.min(...lats), Math.max(...lons), Math.max(...lats)];
}

function mapsAt(lngLat) {
  return maps.filter(
    ({ box }) => lngLat.lng >= box[0] && lngLat.lng <= box[2] && lngLat.lat >= box[1] && lngLat.lat <= box[3]
  );
}

function popupContent(found) {
  const wrapper = document.createElement("div");
  const header = document.createElement("div");
  header.className = "map-list-header";
  header.textContent = found.length === 1 ? "1 map here" : `${found.length} maps here`;
  const list = document.createElement("ul");
  list.className = "map-list";
  for (const item of found) {
    const line = document.createElement("li");
    const title = document.createElement("div");
    title.className = "map-title";
    title.textContent = item.title;
    const path = document.createElement("div");
    path.className = "map-path";
    path.textContent = item.file_path;
    line.append(title, path);
    list.append(line);
  }
  wrapper.append(header, list);
  return wrapper;
}

async function loadMaps({ fit = true } = {}) {
  const summary = document.getElementById("summary-text");
  let collection;
  try {
    const response = await fetch(GEOJSON_URL, { cache: "no-store" });
    if (!response.ok) throw new Error(response.statusText);
    collection = await response.json();
  } catch (error) {
    summary.textContent = "No maps to show yet.";
    return;
  }

  maps = collection.features.map((feature) => ({ ...feature.properties, box: boxOf(feature) }));
  summary.textContent = maps.length === 1 ? "1 map on the globe" : `${maps.length} maps on the globe`;

  // Many maps share an identical box. Draw each distinct box once so stacked copies
  // don't pile up into a solid block; the click list still shows every map.
  const distinct = new Map(collection.features.map((f) => [JSON.stringify(f.geometry), f.geometry]));
  const boxes = {
    type: "FeatureCollection",
    features: [...distinct.values()].map((geometry) => ({ type: "Feature", properties: {}, geometry })),
  };
  if (map.getSource("boxes")) {
    map.getSource("boxes").setData(boxes);
  } else {
    map.addSource("boxes", { type: "geojson", data: boxes });
    map.addLayer({ id: "box-fill", type: "fill", source: "boxes", paint: { "fill-color": BOX_COLOR, "fill-opacity": 0.1 } });
    map.addLayer({ id: "box-outline", type: "line", source: "boxes", paint: { "line-color": BOX_COLOR, "line-width": 2 } });
  }

  if (!fit || !maps.length) return;
  const all = maps.map((m) => m.box);
  map.fitBounds(
    [
      [Math.min(...all.map((b) => b[0])), Math.min(...all.map((b) => b[1]))],
      [Math.max(...all.map((b) => b[2])), Math.max(...all.map((b) => b[3]))],
    ],
    { padding: 80, maxZoom: 9, duration: 0 }
  );
}

// Used by the label screen: redraw after a save, and re-measure when the tab is shown again.
let ready = false; // the map cannot take data until its style has loaded
window.atlasGlobe = {
  reload: () => {
    if (!ready) return; // the first load, still to come, will fetch the latest anyway
    for (const popup of document.querySelectorAll(".maplibregl-popup")) popup.remove();
    return loadMaps({ fit: maps.length === 0 });
  },
  resize: () => map.resize(),
};

map.on("load", () => { ready = true; loadMaps(); });

map.on("click", (event) => {
  const found = mapsAt(event.lngLat);
  if (!found.length) return;
  new maplibregl.Popup({ maxWidth: "360px" }).setLngLat(event.lngLat).setDOMContent(popupContent(found)).addTo(map);
});

map.on("mousemove", (event) => {
  map.getCanvas().style.cursor = mapsAt(event.lngLat).length ? "pointer" : "";
});
