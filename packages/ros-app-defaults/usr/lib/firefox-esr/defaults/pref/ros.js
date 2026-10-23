// Point Firefox at the ROS autoconfig file.
//
// Fonts cannot be set through policies.json: Firefox's Preferences policy only
// accepts prefs from a fixed list of prefixes, and "font." is not one of them.
// autoconfig is the supported way to set any pref as a default.
pref("general.config.filename", "ros.cfg");
pref("general.config.obscure_value", 0);
pref("general.config.sandbox_enabled", false);
