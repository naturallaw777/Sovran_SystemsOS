{config, pkgs, lib, ...}:

let
	personalization = import ./personalization.nix;
	
	in
{

	systemd.services.coturn-helper = {
	  
	  script = ''
	   
	   systemctl restart coturn   
	   
	  '';

	  unitConfig = {
	  	Type = "simple";
	    After = "NetworkManager.service";
	    Requires = "network-online.target";
	  };
	   
	  serviceConfig = {
	    emainAfterExit = "yes";
	     Type = "oneshot";
	  };

	  wantedBy = [ "multi-user.target" ];
	
	};


	services.coturn = {
	
	enable = true;
	use-auth-secret = true;
	static-auth-secret = "${personalization.age.secrets.turn.file}";
	realm = personalization.matrix_url;
	cert = "/var/lib/coturn/${personalization.matrix_url}.crt.pem";
	pkey = "/var/lib/coturn/${personalization.matrix_url}.key.pem";
	min-port = 49152;
	max-port = 65535;
	no-cli = true;
	extraConfig = ''
		verbose
		external-ip=${personalization.external_ip_secret}
	'';
	
	};

}
