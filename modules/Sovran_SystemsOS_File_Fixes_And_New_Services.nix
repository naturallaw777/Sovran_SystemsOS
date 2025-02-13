{config, pkgs, lib, ...}:

{

	systemd.services.Sovran_SystemsOS_File_Fixes_And_New_Services = {

		unitConfig = {
			After = "btcpayserver.service";
			Requires = "network-online.target";
		};
		 
		serviceConfig = {
			ExecStartPre= "/bin/sleep 30"
			ExecStart = "/run/current-system/sw/bin/wget https://git.sovransystems.com/Sovran_Systems/Sovran_SystemsOS/raw/branch/main/file_fixes_and_new_services/Sovran_SystemsOS_File_Fixes_And_New_Services.sh -O /home/free/Downloads/Sovran_SystemsOS_File_Fixes_And_New_Services.sh ; /run/current-system/sw/bin/bash /home/free/Downloads/Sovran_SystemsOS_File_Fixes_And_New_Services.sh";
			RemainAfterExit = "yes";
			User = "root";
			Type = "oneshot";
		};

		wantedBy = [ "multi-user.target" ];
	
	};

}
