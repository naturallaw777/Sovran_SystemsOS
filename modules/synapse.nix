{ config, pkgs, lib, ... }:


####### CREATE NEW USER (ADMIN OR NOT) VIA TERMINAL #######

#  (Run as root in terminal) matrix-synapse-register_new_matrix_user #

####### #######

let
	personalization = import ./personalization.nix;
in
{
	services.matrix-synapse = {
		enable = true;
		settings = {
			include_content = false;
			group_unread_count_by_room = false;
			encryption_enabled_by_default_for_room_type = "invite";
			allow_profile_lookup_over_federation = false;
			allow_device_name_lookup_over_federation = false;
			server_name = personalization.matrix_url;
		 	url_preview_enabled = true;
		 	max_upload_size = "1024M";
		 	url_preview_ip_range_blacklist = [
				"10.0.0.0/8"
				"100.64.0.0/10"
				"169.254.0.0/16"
				"172.16.0.0/12"
				"192.0.0.0/24"
				"192.0.2.0/24"
				"192.168.0.0/16"
				"192.88.99.0/24"
				"198.18.0.0/15"
				"198.51.100.0/24"
				"2001:db8::/32"
				"203.0.113.0/24"
				"224.0.0.0/4"
				"::1/128"
				"fc00::/7"
				"fe80::/10"
				"fec0::/10"
				"ff00::/8"
				];
		 	url_preview_ip_ranger_whitelist = [ "127.0.0.1" ];
		 	turn_shared_secret = "${personalization.turn_shared}";
    		turn_uris = [
      			"turn:${personalization.matrix_url}:5349?transport=udp"
      			"turn:${personalization.matrix_url}:5349?transport=tcp"
      			"turns:${personalization.matrix_url}:5349?transport=udp"
      			"turns:${personalization.matrix_url}:5349?transport=tcp"
          	];
			presence.enabled = true;
			enable_registration = false;
			registration_shared_secret = "${personalization.matrix_reg_secret}";
			listeners = [
				{
					port = 8008;
					bind_addresses = [ "::1" ];
					type = "http";
					tls = false;
					x_forwarded = true;
					resources = [ {
						names = [ "client" ];
						compress = true;
					} 
					{
						names = [ "federation" ];
						compress = false;
					} ];
				}
			];
		};
 	};
}
