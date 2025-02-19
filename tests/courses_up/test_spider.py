from pathlib import Path
from typing import cast

from scrapy import Request
from scrapy.http.response.text import TextResponse

from jg.plucker.courses_up.spider import Spider
from jg.plucker.items import CourseProvider


FIXTURES_DIR = Path(__file__).parent


def test_parse_courses():
    spider = Spider()
    response = TextResponse(
        "https://www.uradprace.cz/api/rekvalifikace/rest/kurz/query-ex",
        body=Path(FIXTURES_DIR / "courses.json").read_bytes(),
    )
    results = list(spider.parse_courses(response, "61989100", 10))

    assert len(results) == 11
    assert all(isinstance(result, CourseProvider) for result in results[:10])
    assert isinstance(results[10], Request)

    course = cast(CourseProvider, results[0])

    assert course["id"] == 20127
    assert (
        course["url"]
        == "https://www.uradprace.cz/web/cz/vyhledani-rekvalifikacniho-kurzu#/rekvalifikacni-kurz-detail/20127"
    )
    assert (
        course["name"]
        == "Linux - správa serveru (+Docker, Kubernetes, VMware) - VMware prezenčně, zbytek distančně"
    )
    assert (
        course["description"]
        == "<p>Stručný obsah: Správa uživatelů a skupin, konfigurační soubory, balení souborů, instalace, správa disků, LVM disky. Utility TCP/IP. Služby Iptables, BIND, Postfix, Samba, NFS, DHCP, Apache. Programování v BASH. Na závěr 2 dny Docker+Kubernetes a 3 dny VMware<br><br>Podrobně:<br>Instalace systému<br>Telnet, ftp, OpenSSH<br>Správa uživatelů a skupin<br>Práce s disky (fdisk, mount, konfigurační soubor fstab)<br>Konfigurační soubory (pořadí startování systému, inittab, rc skripty, inetd, xinetd, MIME, Profily, Logovací soubory, moduly)<br>Balení souborů (tar, gzip), instalace a odinstalace balíčků, utilita rpm, yum, update systému<br>Utility TCP/IP (ifconfig, route, arp, ip, netstat, ping, traceroute, nslookup, host, dig, hostname, tcpdump)<br>Konfigurace GRUBU&nbsp;<br>LVM (správa disků)<br>Tiskárny<br>DHCP server<br>DNS Server<br>Poštovní server<br>Firewall iptables<br>Samba<br>NFS<br>www server Apache<br>POP3, IMAP<br>CentOS7 - Systemd (nově: Rocky Linux)<br>Skriptování v BASH<br>Zabezpečení Linux,LUKS, CA, Fail2ban, SELinux<br><br>Docker<br>-Instalace Dockeru<br>-Vysvětlení základních pojmů jako kontejner, image.<br>-Download image<br>-Spuštění image<br>-Práce s kontejnery<br>-Tvorba image<br>-Připojení k image<br>-Sdílení image<br>-Storage, volumes<br>-Networking, Bridge, Overlay<br><br>Kubernetes<br>-Základní pojmy: Master nod, worker nod<br>-Container runtime, kubelet, kube proxy<br>-Service<br>-ConfigMap<br>-Volumes<br>-Deployments<br>-Kubectl<br><br>prezenčně VMware vSphere<br>- Instalace ESXi serveru<br>- Konzola F2<br>- Základní nastavení ESXi<br>- Instalace vCenter Server Appliance, webový klient<br>- Tvorba uživatelů<br>- Nastavení oprávnění<br>- Konfigurace sítí, standardní switch<br>- Konfigurace úložiště, iSCSI storage<br>- Tvorba a základní konfigurace VM<br>- Tvorba clusteru<br>- vMotion, Migrace VM a úložišť<br>- DRS (Distributed Resource Scheduler) a HA (High Availability)<br>- Šablony VM, klonování<br>- Snapshoty VM<br>- Alerty<br>- Základní monitoring a troubleshooting<br>První den je procvičování podle skript na virtuálních strojích. Další dva dny je výuka.</p>"
    )
    assert (
        course["company_name"] == "Vysoká škola báňská - Technická univerzita Ostrava"
    )
    assert course["business_id"] == "61989100"
