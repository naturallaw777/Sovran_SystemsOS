    def _build_tiles(self):
        method = self._config.get("command_method", "systemctl")
        for entry in self._config.get("services", []):
            tile = ServiceTile(
                name=entry.get("name", entry["unit"]),
                unit=entry["unit"],
                scope=entry.get("type", "system"),
                method=method,
                icon_name=entry.get("icon", ""),
                enabled=entry.get("enabled", True),
            )
            self._flowbox.append(tile)
            self._tiles.append(tile)

        GLib.idle_add(self._refresh_all)