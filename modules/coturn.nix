{config, pkgs, lib, ...}:

let
	personalization = import ./personalization.nix;
	in
{
	systemd.services.sslcoturn = {
		script = ''
			cp -n /var/lib/caddy/.local/share/caddy/certificates/acme.zerossl.com-v2-dv90/${personalization.matrix_url}/${personalization.matrix_url}.crt /var/lib/coturn/${personalization.matrix_url}.crt.pem
			
			cp -n /var/lib/caddy/.local/share/caddy/certificates/acme.zerossl.com-v2-dv90/${personalization.matrix_url}/${personalization.matrix_url}.key /var/lib/coturn/${personalization.matrix_url}.key.pem
			
			chown turnserver:turnserver /var/lib/coturn -R

			chmod 770 /var/lib/coturn -R

			systemctl restart coturn	
		'';

		unitConfig = {
			Type = "simple";
			After = "NetworkManager.service";
			Requires = "network-online.target";
		};
	
		serviceConfig = {
			RemainAfterExit = "yes";
			Type = "oneshot";
	   };

		wantedBy = [ "multi-user.target" ];
	};


	services.coturn = {
		enable = true;
		use-auth-secret = true;
		static-auth-secret = "${age.secrets.turn.file}";
		realm = personalization.matrix_url;
		cert = "/var/lib/coturn/${personalization.matrix_url}.crt.pem";
		pkey = "/var/lib/coturn/${personalization.matrix_url}.key.pem";
		min-port = 49152;
		max-port = 65535;
		no-cli = true;
		#listening-ips = [ "127.0.0.1" ];
		extraConfig = ''
			verbose
			external-ip=${personalization.external_ip_secret}
		'';
	};
}
