    case "$service" in
        wordpress)
            echo -e "  ${BOLD}WordPress has been fully configured.${NC}"
            echo ""
            echo "  View your admin credentials:"
            echo -e "    ${CYAN}sovran-manage show-creds wordpress${NC}"
            echo ""
            echo -e "  Login at: ${CYAN}https://${domain}/wp-admin/${NC}"
            echo ""
            echo "  Manage plugins:"
            echo -e "    ${CYAN}sovran-manage wp plugin install woocommerce --activate${NC}"
            echo -e "    ${CYAN}sovran-manage wp plugin list${NC}"
            echo -e "    ${CYAN}sovran-manage wp theme install flavor flavor --activate${NC}"
            echo ""
            ;;

        nextcloud)
            echo -e "  ${BOLD}Nextcloud has been fully configured.${NC}"
            echo ""
            echo "  Pre-installed apps: Calendar, Contacts, Tasks, Notes, Deck"
            echo ""
            echo "  View your admin credentials:"
            echo -e "    ${CYAN}sovran-manage show-creds nextcloud${NC}"
            echo ""
            echo -e "  Login at: ${CYAN}https://${domain}/${NC}"
            echo ""
            echo "  Manage apps:"
            echo -e "    ${CYAN}sovran-manage occ app:install cookbook${NC}"
            echo -e "    ${CYAN}sovran-manage occ app:list${NC}"
            echo ""
            ;;

        matrix)
            echo -e "  Matrix Synapse is running."
            echo -e "  URL: ${CYAN}https://${domain}${NC}"
            echo ""
            echo "  Create your first user:"
            echo -e "    ${CYAN}sovran-manage matrix register-user${NC}"
            echo ""
            ;;

        *)
            echo -e "  URL: ${CYAN}https://${domain}${NC}"
            echo ""
            ;;
    esac