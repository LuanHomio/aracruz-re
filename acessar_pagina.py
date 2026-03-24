"""
Script básico para acessar uma página web usando Selenium
"""
try:
    import undetected_chromedriver as uc
    UC_AVAILABLE = True
except ImportError:
    UC_AVAILABLE = False
    print("undetected-chromedriver não disponível, usando Selenium padrão")

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import time
import os
import random
import shutil
from pathlib import Path

def is_driver_active(driver):
    try:
        driver.current_url
        return True
    except:
        return False

def acessar_pagina(url):
    """
    Acessa uma página web usando Selenium com Chrome
    """
    # Configurar opções do Chrome
    # Se usar undetected-chromedriver, ele já tem opções anti-detecção embutidas
    chrome_options = Options()
    # Descomente a linha abaixo se quiser executar em modo headless (sem abrir o navegador)
    # chrome_options.add_argument("--headless")
    
    # Adicionar opções para WSL/Linux
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    
    # Configurar diretórios de download (usar caminho absoluto)
    download_dir = os.path.abspath(os.path.join(os.getcwd(), "downloads"))
    download_clientes_dir = os.path.abspath(os.path.join(download_dir, "clientes"))
    download_sales_dir = os.path.abspath(os.path.join(download_dir, "sales"))
    download_holds_dir = os.path.abspath(os.path.join(download_dir, "holds"))
    
    os.makedirs(download_dir, exist_ok=True)
    os.makedirs(download_clientes_dir, exist_ok=True)
    os.makedirs(download_sales_dir, exist_ok=True)
    os.makedirs(download_holds_dir, exist_ok=True)
    
    print(f"Diretório de download configurado: {download_dir}")
    print(f"  - Clientes: {download_clientes_dir}")
    print(f"  - Sales: {download_sales_dir}")
    print(f"  - Holds: {download_holds_dir}")
    
    # Configurar preferências de download
    prefs = {
        "download.default_directory": download_dir,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True,
        "profile.default_content_setting_values.automatic_downloads": 1
    }
    chrome_options.add_experimental_option("prefs", prefs)
    
    # Opções anti-detecção apenas se NÃO usar undetected-chromedriver
    if not UC_AVAILABLE:
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        # User agent real para parecer um navegador normal
        chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    # Configurar o ChromeDriver apenas se não estiver usando undetected-chromedriver
    driver_path = None
    if not UC_AVAILABLE:
        # Configurar o serviço do ChromeDriver
        # Desabilitar logs do webdriver-manager
        os.environ['WDM_LOG_LEVEL'] = '0'
        os.environ['WDM_PRINT_FIRST_LINE'] = 'False'
        
        # Baixar e configurar o ChromeDriver
        # O webdriver-manager tentará detectar a versão do Chrome ou usar a mais recente
        try:
            driver_path = ChromeDriverManager().install()
            
            # Verificar se o caminho retornado é realmente o executável chromedriver
            # O webdriver-manager às vezes retorna o caminho errado
            driver_dir = os.path.dirname(driver_path)
            
            # Se o caminho retornado contém "THIRD_PARTY" ou não é executável, procurar o correto
            is_windows = os.name == 'nt'
            chromedriver_name = "chromedriver.exe" if is_windows else "chromedriver"
            
            if "THIRD_PARTY" in driver_path or not driver_path.endswith(chromedriver_name) or driver_path.endswith(".chromedriver"):
                # Procurar pelo arquivo chromedriver no diretório
                chromedriver_executable = os.path.join(driver_dir, chromedriver_name)
                if os.path.isfile(chromedriver_executable):
                    driver_path = chromedriver_executable
                else:
                    # Procurar recursivamente no diretório pai (webdriver-manager pode colocar em subdiretório)
                    parent_dir = os.path.dirname(driver_dir) if "THIRD_PARTY" in driver_path else driver_dir
                    found = False
                    for root, dirs, files in os.walk(parent_dir):
                        for file in files:
                            if file == chromedriver_name:
                                full_path = os.path.join(root, file)
                                if os.path.isfile(full_path):
                                    driver_path = full_path
                                    found = True
                                    break
                        if found:
                            break
            
            # Garantir que o arquivo existe e é executável
            if not os.path.isfile(driver_path):
                raise FileNotFoundError(f"ChromeDriver não encontrado em: {driver_path}")
            
            if not is_windows:
                os.chmod(driver_path, 0o755)
            print(f"ChromeDriver configurado: {driver_path}")
            
        except AttributeError as e:
            if "'NoneType' object has no attribute 'split'" in str(e):
                print("\n" + "="*60)
                print("ERRO: Google Chrome não está instalado!")
                print("="*60)
                print("\nPara instalar o Chrome no WSL, execute:")
                print("  ./instalar_chrome.sh")
                print("\nOu instale manualmente:")
                print("  sudo apt-get update")
                print("  sudo apt-get install -y wget gnupg")
                print("  wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | sudo apt-key add -")
                print('  echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" | sudo tee /etc/apt/sources.list.d/google-chrome.list')
                print("  sudo apt-get update")
                print("  sudo apt-get install -y google-chrome-stable")
                print("="*60 + "\n")
            raise
        except Exception as e:
            print(f"\nErro ao configurar ChromeDriver: {e}")
            print("\nIMPORTANTE: É necessário ter o Google Chrome instalado!")
            print("Para instalar no WSL, execute: ./instalar_chrome.sh")
            raise
    
    # Criar instância do navegador
    # Usar undetected-chromedriver se disponível (melhor para evitar detecção)
    if UC_AVAILABLE:
        print("Configurando ambiente para VPS (Perfil persistente local)...")
        
        uc_options = uc.ChromeOptions()
        
        # Criar um perfil fixo NA VPS para acumular "reputação" e cookies
        profile_path = os.path.abspath(os.path.join(os.getcwd(), "bot_profile"))
        os.makedirs(profile_path, exist_ok=True)
        
        uc_options.add_argument(f'--user-data-dir={profile_path}')
        uc_options.add_argument("--no-sandbox")
        uc_options.add_argument("--disable-dev-shm-usage")
        uc_options.add_argument("--window-size=1920,1080")
        
        # Não desabilitamos a GPU pois o Cloudflare checa isso para detectar bots
        
        # Configurar diretórios de download
        download_dir = os.path.abspath(os.path.join(os.getcwd(), "downloads"))
        os.makedirs(download_dir, exist_ok=True)
        
        prefs = {
            "download.default_directory": download_dir,
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
            "safebrowsing.enabled": True,
            "profile.default_content_setting_values.automatic_downloads": 1
        }
        uc_options.add_experimental_option("prefs", prefs)
        
        driver = uc.Chrome(options=uc_options, use_subprocess=True)
    else:
        # Criar o serviço do ChromeDriver
        service = Service(driver_path)
        driver = webdriver.Chrome(service=service, options=chrome_options)
        
        # Remover propriedades que indicam automação
        driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
            'source': '''
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [1, 2, 3, 4, 5]
                });
                Object.defineProperty(navigator, 'languages', {
                    get: () => ['pt-BR', 'pt', 'en-US', 'en']
                });
            '''
        })
    
    try:
        # Criar WebDriverWait para usar em várias partes
        wait = WebDriverWait(driver, 60)
        actions = ActionChains(driver)
        
        print(f"Acessando a página: {url}")
        driver.get(url)
        
        # Aguardar um pouco para a página carregar
        print("Aguardando página carregar...")
        time.sleep(2)
        
        # Verificar se há verificação do Cloudflare
        print("Verificando se há verificação do Cloudflare...")
        
        # Mover o mouse por 3 segundos para simular atividade humana
        print("Movendo o cursor por 3 segundos...")
        start_time = time.time()
        window_size = driver.get_window_size()
        max_x = window_size['width']
        max_y = window_size['height']
        
        # Obter o body para mover o mouse sobre ele
        try:
            body = driver.find_element(By.TAG_NAME, "body")
        except:
            body = None
        
        movements = 0
        while time.time() - start_time < 3:
            # Mover para uma posição aleatória
            x_offset = random.randint(-200, 200)
            y_offset = random.randint(-200, 200)
            
            if body:
                try:
                    actions.move_to_element_with_offset(body, x_offset, y_offset).perform()
                except:
                    actions.move_by_offset(x_offset, y_offset).perform()
            else:
                actions.move_by_offset(x_offset, y_offset).perform()
            
            time.sleep(0.15)
            movements += 1
        
        print(f"Movimento do cursor concluído ({movements} movimentos).")
        
        # Aguardar um pouco antes de procurar elementos do Cloudflare
        print("Aguardando Cloudflare carregar...")
        time.sleep(3)
        
        # Verificar se há verificação do Cloudflare
        max_wait_time = 60  # Aumentar tempo de espera para 60 segundos
        start_wait = time.time()
        cloudflare_passed = False
        
        print("Aguardando verificação do Cloudflare passar...")
        print("(O Cloudflare Turnstile completa automaticamente, não precisa de clique)")
        
        # Verificar se há iframe do Turnstile
        turnstile_iframe_selectors = [
            "iframe[src*='challenges.cloudflare.com']",
            "iframe[src*='turnstile']",
            "iframe[title*='challenge']",
            "iframe[title*='Cloudflare']",
            "iframe[id*='cf-chl']",
            "iframe[data-sitekey]",
            "iframe[class*='cf-']",
            "iframe[class*='turnstile']",
        ]
        
        turnstile_found = False
        turnstile_iframe = None
        for iframe_selector in turnstile_iframe_selectors:
            try:
                iframes = driver.find_elements(By.CSS_SELECTOR, iframe_selector)
                if iframes:
                    print(f"iframe do Cloudflare Turnstile encontrado: {iframe_selector}")
                    turnstile_found = True
                    turnstile_iframe = iframes[0]
                    break
            except:
                continue
        
        # Se não encontrou com seletores específicos, procurar todos os iframes
        if not turnstile_found:
            try:
                all_iframes = driver.find_elements(By.TAG_NAME, "iframe")
                for iframe in all_iframes:
                    try:
                        src = iframe.get_attribute("src") or ""
                        if "cloudflare" in src.lower() or "turnstile" in src.lower() or "challenge" in src.lower():
                            print(f"iframe do Cloudflare encontrado por src: {src}")
                            turnstile_found = True
                            turnstile_iframe = iframe
                            break
                    except:
                        continue
            except:
                pass
        
        # Procurar também por checkbox fora do iframe (alguns casos)
        cloudflare_checkbox_selectors = [
            "input[type='checkbox']",
            ".cb-lb",
            "#challenge-form input[type='checkbox']",
            "label[for*='challenge']",
        ]
        
        # Loop principal de espera
        loop_count = 0
        while time.time() - start_wait < max_wait_time:
            loop_count += 1
            # Verificar se o driver ainda está ativo
            if not is_driver_active(driver):
                print("❌ ERRO: Navegador foi fechado durante a espera do Cloudflare!")
                raise Exception("Sessão do navegador foi perdida")
            
            # Verificar se o título mudou (Cloudflare passou)
            try:
                current_title = driver.title
                current_url = driver.current_url
            except Exception as e:
                print(f"❌ ERRO: Não foi possível acessar informações da página: {e}")
                raise
            
            # Re-procurar o iframe do Turnstile a cada 5 iterações (caso apareça depois)
            if loop_count % 5 == 0 and not turnstile_found:
                print("Re-procurando iframe do Turnstile...")
                for iframe_selector in turnstile_iframe_selectors:
                    try:
                        iframes = driver.find_elements(By.CSS_SELECTOR, iframe_selector)
                        if iframes:
                            print(f"iframe do Cloudflare Turnstile encontrado agora: {iframe_selector}")
                            turnstile_found = True
                            turnstile_iframe = iframes[0]
                            break
                    except:
                        continue
            
            # Verificar múltiplas condições para saber se passou
            title_changed = current_title != "Just a moment..." and "moment" not in current_title.lower()
            url_changed = "challenges.cloudflare.com" not in current_url
            
            # Verificar se o campo de login apareceu (sinal de que passou)
            try:
                login_field = driver.find_elements(By.ID, "cLogin_dbUsername")
                if login_field:
                    print("Campo de login encontrado! Cloudflare passou!")
                    cloudflare_passed = True
                    break
            except:
                pass
            
            if title_changed and url_changed:
                print("Título e URL mudaram! Cloudflare passou!")
                cloudflare_passed = True
                break
            
            # Tentar encontrar e clicar no checkbox fora do iframe (se existir)
            if not turnstile_found:
                for cb_selector in cloudflare_checkbox_selectors:
                    try:
                        checkbox = driver.find_elements(By.CSS_SELECTOR, cb_selector)
                        if checkbox and checkbox[0].is_displayed():
                            print(f"Checkbox do Cloudflare encontrado fora do iframe! Clicando...")
                            actions.move_to_element(checkbox[0]).pause(0.5).click().perform()
                            print("Clicou no checkbox do Cloudflare!")
                            time.sleep(2)
                            # Verificar se passou
                            if driver.title != "Just a moment...":
                                cloudflare_passed = True
                                break
                    except:
                        continue
            
            # Se encontrou o Turnstile, tentar interagir com ele
            if turnstile_found and turnstile_iframe:
                try:
                    # Mover o mouse sobre o iframe do Turnstile para simular interação humana
                    try:
                        print("Movendo mouse sobre o iframe do Turnstile...")
                        actions.move_to_element(turnstile_iframe).pause(0.5).perform()
                        time.sleep(1)
                    except:
                        pass
                    
                    # Tentar clicar no iframe do Turnstile (alguns casos o clique no iframe funciona)
                    try:
                        print("Clicando no iframe do Turnstile...")
                        actions.move_to_element(turnstile_iframe).pause(0.3).click().pause(0.5).perform()
                        time.sleep(2)
                    except:
                        pass
                    
                    # Procurar pelo checkbox do Cloudflare dentro do iframe
                    try:
                        driver.switch_to.frame(turnstile_iframe)
                        
                        # Seletores mais específicos do Turnstile
                        checkbox_selectors = [
                            "input[type='checkbox']",
                            ".cb-lb",
                            "#challenge-form input[type='checkbox']",
                            "label[for*='challenge']",
                            "label[for*='cb']",
                            ".mark",
                            "[role='checkbox']",
                            "div[class*='checkbox']",
                            "span[class*='checkbox']",
                        ]
                        
                        checkbox_found = False
                        for cb_selector in checkbox_selectors:
                            try:
                                checkbox = driver.find_elements(By.CSS_SELECTOR, cb_selector)
                                if checkbox:
                                    print(f"Checkbox do Cloudflare encontrado dentro do iframe! Clicando...")
                                    # Mover mouse até o checkbox e clicar
                                    actions.move_to_element(checkbox[0]).pause(0.3).click().pause(0.5).perform()
                                    print("Clicou no checkbox do Cloudflare!")
                                    checkbox_found = True
                                    time.sleep(2)
                                    break
                            except:
                                continue
                        
                        # Se não encontrou checkbox, tentar clicar em qualquer elemento clicável
                        if not checkbox_found:
                            try:
                                clickable_elements = driver.find_elements(By.CSS_SELECTOR, "div, span, label, button")
                                for elem in clickable_elements[:5]:
                                    try:
                                        if elem.is_displayed() and elem.is_enabled():
                                            print("Clicando em elemento clicável do Turnstile...")
                                            actions.move_to_element(elem).pause(0.3).click().pause(0.5).perform()
                                            time.sleep(2)
                                            break
                                    except:
                                        continue
                            except:
                                pass
                        
                        driver.switch_to.default_content()
                        
                        # Aguardar um pouco após clicar
                        time.sleep(2)
                        
                        # Verificar se passou após o clique
                        if driver.title != "Just a moment..." and "moment" not in driver.title.lower():
                            print("Cloudflare passou após interagir com o Turnstile!")
                            cloudflare_passed = True
                            break
                    except Exception as e:
                        try:
                            driver.switch_to.default_content()
                        except:
                            pass
                        print(f"Erro ao interagir com iframe: {e}")
                        continue
                    
                    # Verificar se o token do Turnstile foi gerado (campo hidden preenchido)
                    try:
                        turnstile_response = driver.find_elements(By.CSS_SELECTOR, "input[name='cf-turnstile-response']")
                        if turnstile_response and turnstile_response[0].get_attribute('value'):
                            print("Token do Turnstile gerado! Aguardando redirecionamento...")
                            time.sleep(3)
                            # Verificar novamente se passou
                            if driver.title != "Just a moment...":
                                cloudflare_passed = True
                                break
                    except:
                        pass
                except:
                    pass
            
            # Verificar se o driver ainda está ativo antes de continuar
            if not is_driver_active(driver):
                print("❌ ERRO: Navegador foi fechado durante a espera do Cloudflare!")
                raise Exception("Sessão do navegador foi perdida")
            
            # Se encontrou o Turnstile, fazer mais movimento do mouse sobre ele para simular comportamento humano
            if turnstile_found and turnstile_iframe:
                try:
                    # Movimento aleatório sobre o iframe
                    actions.move_to_element_with_offset(turnstile_iframe, random.randint(-10, 10), random.randint(-10, 10)).pause(0.2).perform()
                except:
                    pass
            
            # Aguardar um pouco antes de verificar novamente
            time.sleep(2)
            
            # Mostrar progresso a cada 10 segundos
            elapsed = int(time.time() - start_wait)
            if elapsed % 10 == 0 and elapsed > 0:
                print(f"Aguardando... ({elapsed}s/{max_wait_time}s)")
        
        if not cloudflare_passed:
            print(f"Tempo de espera esgotado ({max_wait_time}s). Tentando continuar mesmo assim...")
            time.sleep(3)
        
        # Verificar se o driver ainda está ativo antes da verificação final
        if not is_driver_active(driver):
            print("❌ ERRO: Navegador foi fechado durante a espera do Cloudflare!")
            raise Exception("Sessão do navegador foi perdida")
        
        # Verificação final antes de tentar login
        print("\n" + "="*60)
        print("Verificação final do status da página:")
        try:
            print(f"Título da página: {driver.title}")
            print(f"URL atual: {driver.current_url}")
        except Exception as e:
            print(f"❌ ERRO ao verificar status da página: {e}")
            raise
        print("="*60 + "\n")
        
        # Verificar se ainda está na página do Cloudflare
        if "Just a moment" in driver.title or "challenges.cloudflare.com" in driver.current_url:
            print("⚠️  ATENÇÃO: Ainda parece estar na página do Cloudflare!")
            print("Aguardando mais 10 segundos...")
            time.sleep(10)
            
            # Verificar novamente
            if "Just a moment" in driver.title:
                print("❌ ERRO: Não foi possível passar pelo Cloudflare automaticamente.")
                print("O Cloudflare pode estar bloqueando automação.")
                print("O Cloudflare pode estar bloqueando automação nesta tentativa.")
                raise Exception("Cloudflare não passou após aguardar")
        
        # Fazer login (apenas se necessário)
        print("Verificando se login é necessário...")
        
        # Verificar se já estamos logados ou se o campo de login não existe
        try:
            # Procurar o campo de usuário com um timeout curto (3 segundos) para não travar o bot
            driver.implicitly_wait(3)
            campo_usuario_existente = driver.find_elements(By.ID, "cLogin_dbUsername")
            driver.implicitly_wait(10) # Volta o timeout padrão
            
            if not campo_usuario_existente:
                print("✅ Sessão já ativa ou redirecionado direto para a área interna. Pulando login...")
            else:
                print("Realizando login...")
                # Aguardar até 30 segundos pelo campo de usuário
                campo_usuario = wait.until(
                    EC.presence_of_element_located((By.ID, "cLogin_dbUsername"))
                )
                
                # Clicar no campo de usuário e preencher
                campo_usuario.click()
                campo_usuario.clear()
                campo_usuario.send_keys("EAndriao")
                print("Usuário preenchido: EAndriao")
                
                # Aguardar um pouco
                time.sleep(1)
                
                # Aguardar e encontrar o campo de senha
                campo_senha = wait.until(
                    EC.presence_of_element_located((By.ID, "cLogin_dbPassword"))
                )
                
                # Clicar no campo de senha e preencher
                campo_senha.click()
                campo_senha.clear()
                campo_senha.send_keys("Dudu1976")
                print("Senha preenchida")
                
                # Aguardar um pouco antes de clicar no botão de login
                time.sleep(1)
                
                # Clicar no botão de login
                print("Clicando no botão de login...")
                botao_login = wait.until(
                    EC.element_to_be_clickable((By.ID, "buttonLogin"))
                )
                
                # Mover mouse até o botão e clicar
                actions.move_to_element(botao_login).pause(0.5).click().perform()
                print("Botão de login clicado!")
                
                # Aguardar um pouco para a página processar o login
                time.sleep(3)
        except Exception as e:
            print(f"Nota: Fluxo de login pulado ou erro ao tentar (pode já estar logado): {e}")
            driver.implicitly_wait(10) # Garante que o wait volte ao normal se houver erro
        
        # Verificar o status após (tentativa de) login
        print(f"Título da página: {driver.title}")
        print(f"URL atual: {driver.current_url}")
        
        # Aguardar a página carregar completamente
        time.sleep(2)
        
        print("\nAjustando Status de 'Active' para 'All'...")
        try:
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "#s2id_Status a.select2-choice")))
            status_dropdown = driver.find_element(By.CSS_SELECTOR, "#s2id_Status a.select2-choice")
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", status_dropdown)
            time.sleep(0.5)
            
            actions.move_to_element(status_dropdown).pause(0.3).click().perform()
            time.sleep(1)

            wait.until(EC.presence_of_element_located((By.XPATH, "//div[contains(@class,'select2-drop-active')]")))
            
            opcao_all = driver.find_element(By.XPATH, "//li[contains(@class,'select2-result-selectable')][contains(.,'All')]")
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", opcao_all)
            time.sleep(0.3)
            actions.move_to_element(opcao_all).pause(0.3).click().perform()
            time.sleep(2)

            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "table tr td")))
            time.sleep(2)
            print("✅ Status alterado para 'All' e tabela carregada.")

        except Exception as e:
            print(f"❌ Erro ao ajustar Status para 'All': {e}")
            raise
        
        # Procurar e clicar na imagem do CSV
        print("\nProcurando pela imagem do CSV...")
        img_csv_selectors = [
            "img[src*='CSV.png']",
            "img[src*='csv.png']",
            "img[src='image/CSV.png']",
            "img[src='/image/CSV.png']",
        ]
        
        img_csv_encontrada = False
        for selector in img_csv_selectors:
            try:
                img_csv = driver.find_elements(By.CSS_SELECTOR, selector)
                if img_csv:
                    print(f"Imagem do CSV encontrada! ({selector})")
                    # Aguardar que a imagem esteja visível e clicável
                    img_element = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, selector)))
                    
                    # Mover mouse até a imagem e clicar
                    actions.move_to_element(img_element).pause(0.5).click().perform()
                    print("Clicou na imagem do CSV!")
                    img_csv_encontrada = True
                    break
            except Exception as e:
                continue
        
        if not img_csv_encontrada:
            print("⚠️  Imagem do CSV não encontrada. Tentando procurar por qualquer imagem com 'CSV' no src...")
            try:
                # Procurar por qualquer img que contenha CSV
                all_imgs = driver.find_elements(By.TAG_NAME, "img")
                for img in all_imgs:
                    src = img.get_attribute("src") or ""
                    if "CSV" in src.upper() or "csv" in src.lower():
                        print(f"Imagem do CSV encontrada por busca ampla: {src}")
                        actions.move_to_element(img).pause(0.5).click().perform()
                        print("Clicou na imagem do CSV!")
                        img_csv_encontrada = True
                        break
            except Exception as e:
                print(f"Erro ao procurar imagem do CSV: {e}")
        
        if img_csv_encontrada:
            # Aguardar o download do arquivo CSV
            print("Aguardando download do arquivo CSV de clientes...")
            download_clientes_dir = os.path.abspath(os.path.join(os.getcwd(), "downloads", "clientes"))
            print(f"Procurando arquivo em: {download_clientes_dir}")
            
            # Também verificar diretórios padrão do Chrome no Linux
            possiveis_diretorios = [
                download_clientes_dir,
                os.path.abspath(os.path.join(os.getcwd(), "downloads")),
                os.path.expanduser("~/Downloads"),
                os.path.expanduser("~/downloads"),
                "/tmp",
            ]
            
            # Aguardar até que o arquivo seja baixado (máximo 30 segundos)
            max_wait_download = 30
            start_download = time.time()
            arquivo_baixado = None
            
            while time.time() - start_download < max_wait_download:
                # Procurar em todos os diretórios possíveis
                for dir_path in possiveis_diretorios:
                    if not os.path.exists(dir_path):
                        continue
                    
                    # Listar arquivos CSV no diretório
                    try:
                        arquivos = list(Path(dir_path).glob("*.csv"))
                        if arquivos:
                            # Pegar o arquivo mais recente
                            arquivo_mais_recente = max(arquivos, key=os.path.getctime)
                            # Verificar se foi modificado recentemente (últimos 30 segundos)
                            tempo_modificacao = time.time() - os.path.getmtime(arquivo_mais_recente)
                            if tempo_modificacao < 30:
                                arquivo_baixado = arquivo_mais_recente
                                print(f"Arquivo CSV encontrado em: {dir_path}")
                                print(f"Nome do arquivo: {arquivo_baixado.name}")
                                break
                    except Exception as e:
                        continue
                
                if arquivo_baixado:
                    break
                
                # Verificar também por arquivos .crdownload (download em andamento)
                for dir_path in possiveis_diretorios:
                    if not os.path.exists(dir_path):
                        continue
                    try:
                        arquivos_em_download = list(Path(dir_path).glob("*.crdownload"))
                        if arquivos_em_download:
                            print(f"Download em andamento em: {dir_path}")
                            break
                    except:
                        continue
                
                time.sleep(1)
            
            if arquivo_baixado:
                # Se o arquivo não está no diretório de clientes, mover para lá
                if str(arquivo_baixado.parent) != download_clientes_dir:
                    print(f"Movendo arquivo de {arquivo_baixado.parent} para {download_clientes_dir}...")
                
                # Renomear o arquivo com timestamp para evitar sobrescrita
                timestamp = time.strftime("%Y%m%d_%H%M%S")
                novo_nome = f"clientes_{timestamp}.csv"
                caminho_final = os.path.join(download_clientes_dir, novo_nome)
                
                # Se o arquivo já existe com esse nome, adicionar número
                contador = 1
                while os.path.exists(caminho_final):
                    novo_nome = f"clientes_{timestamp}_{contador}.csv"
                    caminho_final = os.path.join(download_clientes_dir, novo_nome)
                    contador += 1
                
                # Mover o arquivo para o diretório de download com o novo nome
                shutil.move(str(arquivo_baixado), caminho_final)
                print(f"✅ Arquivo CSV salvo em: {caminho_final}")
                print(f"   Tamanho: {os.path.getsize(caminho_final)} bytes")
            else:
                print("⚠️  Arquivo CSV não foi baixado no tempo esperado.")
                print(f"   Verifique manualmente os diretórios: {', '.join(possiveis_diretorios)}")
        else:
            print("⚠️  Não foi possível encontrar a imagem do CSV para clicar.")
        
        # ========== BAIXAR HOLDS ==========
        print("\n" + "="*60)
        print("INICIANDO DOWNLOAD DE HOLDS")
        print("="*60)
        
        try:
            print("\n1. Clicando em 'Sales'...")
            try:
                link_sales = wait.until(
                    EC.element_to_be_clickable((By.XPATH, "//a[@href='/vSalesHome.aspx']"))
                )
                driver.execute_script("arguments[0].scrollIntoView(true);", link_sales)
                time.sleep(0.5)
                actions.move_to_element(link_sales).pause(0.3).click().perform()
                print("✅ Clicou em 'Sales'")
                time.sleep(2)
            except Exception as e:
                print(f"⚠️  Erro ao clicar em 'Sales': {e}")
                try:
                    link_sales = driver.find_element(By.XPATH, "//a[contains(text(), 'Sales')]")
                    driver.execute_script("arguments[0].scrollIntoView(true);", link_sales)
                    time.sleep(0.5)
                    actions.move_to_element(link_sales).pause(0.3).click().perform()
                    print("✅ Clicou em 'Sales' (método alternativo)")
                    time.sleep(2)
                except:
                    raise Exception("Não foi possível encontrar o link 'Sales'")
            
            print("\n2. Clicando em 'Holds' (sidebar, não 'On Credit Hold')...")
            try:
                link_holds = wait.until(
                    EC.element_to_be_clickable((By.LINK_TEXT, "Holds"))
                )
                driver.execute_script("arguments[0].scrollIntoView(true);", link_holds)
                time.sleep(0.5)
                driver.execute_script("arguments[0].click();", link_holds)
                print("✅ Clicou em 'Holds'")
                time.sleep(2)
            except Exception as e:
                print(f"⚠️  Erro ao clicar em 'Holds': {e}")
                try:
                    link_holds = driver.find_element(By.XPATH, "//a[contains(@href,'listOpportunities') and contains(@href,'tab=5')]")
                    driver.execute_script("arguments[0].click();", link_holds)
                    print("✅ Clicou em 'Holds' (href listOpportunities tab=5)")
                except:
                    try:
                        link_holds = driver.find_element(By.XPATH, "//a[contains(@href,'Hold') and not(contains(@href,'Credit'))]")
                        driver.execute_script("arguments[0].click();", link_holds)
                        print("✅ Clicou em 'Holds' (excluindo On Credit Hold)")
                    except:
                        raise Exception("Não foi possível encontrar 'Holds'")
            
            print("\n3. Clicando em 'All' (Holds)...")
            try:
                link_all_holds = wait.until(
                    EC.element_to_be_clickable((By.XPATH, "//a[@class='underline' and contains(@title, 'Show All')]"))
                )
                driver.execute_script("arguments[0].scrollIntoView(true);", link_all_holds)
                time.sleep(0.5)
                actions.move_to_element(link_all_holds).pause(0.3).click().perform()
                print("✅ Clicou em 'All' (Holds)")
                time.sleep(5)
            except Exception as e:
                print(f"⚠️  Erro ao clicar em 'All' (Holds): {e}")
                try:
                    link_all_holds = driver.find_element(By.XPATH, "//a[(contains(@href, 'listOpportunities') or contains(@href, 'ListHold')) and contains(text(), 'All')]")
                    driver.execute_script("arguments[0].click();", link_all_holds)
                    print("✅ Clicou em 'All' (método alternativo)")
                    time.sleep(5)
                except:
                    raise Exception("Não foi possível encontrar o link 'All' na página de Holds")
            
            print("\n4. Clicando na imagem do Excel para baixar Holds...")
            download_holds_dir = os.path.abspath(os.path.join(os.getcwd(), "downloads", "holds"))
            time.sleep(2)
            
            img_excel_holds_selectors = [
                "img[src*='icon_excel.gif']",
                "img[src*='excel']",
                "a[title='Export to Excel']",
                "a[title='Export to Excel'] img",
            ]
            
            img_excel_holds_encontrada = False
            for selector in img_excel_holds_selectors:
                try:
                    elems = driver.find_elements(By.CSS_SELECTOR, selector)
                    for elem in elems:
                        try:
                            target = elem if elem.tag_name == "a" else elem.find_element(By.XPATH, "./ancestor::a[1]")
                            if target and target.is_displayed():
                                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", target)
                                time.sleep(1)
                                driver.execute_script("arguments[0].click();", target)
                                print("✅ Clicou no export Excel (Holds)")
                                img_excel_holds_encontrada = True
                                break
                        except:
                            if elem.is_displayed():
                                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", elem)
                                time.sleep(1)
                                driver.execute_script("arguments[0].click();", elem)
                                print("✅ Clicou no export Excel (Holds)")
                                img_excel_holds_encontrada = True
                                break
                    if img_excel_holds_encontrada:
                        break
                except:
                    continue
            
            if not img_excel_holds_encontrada:
                all_imgs = driver.find_elements(By.TAG_NAME, "img")
                for img in all_imgs:
                    try:
                        src = img.get_attribute("src") or ""
                        if "excel" in src.lower():
                            link_excel = img.find_element(By.XPATH, "./ancestor::a[1]")
                            if link_excel.is_displayed():
                                driver.execute_script("arguments[0].click();", link_excel)
                                print("✅ Clicou no export Excel (busca ampla)")
                                img_excel_holds_encontrada = True
                                break
                    except:
                        continue
            
            if img_excel_holds_encontrada:
                print("Aguardando download do arquivo Excel de holds...")
                possiveis_diretorios_holds = [
                    download_holds_dir,
                    os.path.abspath(os.path.join(os.getcwd(), "downloads")),
                    os.path.expanduser("~/Downloads"),
                    os.path.expanduser("~/downloads"),
                    "/tmp",
                ]
                max_wait_download = 60
                start_download = time.time()
                arquivo_baixado_holds = None
                arquivos_antes_holds = {}
                for dir_path in possiveis_diretorios_holds:
                    if os.path.exists(dir_path):
                        try:
                            arquivos_antes_holds[dir_path] = set(Path(dir_path).glob("*.xls*"))
                        except:
                            arquivos_antes_holds[dir_path] = set()
                
                while time.time() - start_download < max_wait_download:
                    for dir_path in possiveis_diretorios_holds:
                        if not os.path.exists(dir_path):
                            continue
                        try:
                            arquivos_atuais = set(Path(dir_path).glob("*.xls*"))
                            arquivos_novos = arquivos_atuais - arquivos_antes_holds.get(dir_path, set())
                            if arquivos_novos:
                                arquivo_mais_recente = max(arquivos_novos, key=os.path.getctime)
                                if time.time() - os.path.getmtime(arquivo_mais_recente) < 60:
                                    arquivo_baixado_holds = arquivo_mais_recente
                                    break
                            if not arquivo_baixado_holds and arquivos_atuais:
                                arquivo_mais_recente = max(arquivos_atuais, key=os.path.getmtime)
                                if time.time() - os.path.getmtime(arquivo_mais_recente) < 60:
                                    arquivo_baixado_holds = arquivo_mais_recente
                                    break
                        except:
                            continue
                    if arquivo_baixado_holds:
                        break
                    time.sleep(1)
                
                if arquivo_baixado_holds:
                    if str(arquivo_baixado_holds.parent) != download_holds_dir:
                        print(f"Movendo arquivo de {arquivo_baixado_holds.parent} para {download_holds_dir}...")
                    timestamp = time.strftime("%Y%m%d_%H%M%S")
                    extensao = arquivo_baixado_holds.suffix
                    novo_nome = f"holds_{timestamp}{extensao}"
                    caminho_final_holds = os.path.join(download_holds_dir, novo_nome)
                    contador = 1
                    while os.path.exists(caminho_final_holds):
                        novo_nome = f"holds_{timestamp}_{contador}{extensao}"
                        caminho_final_holds = os.path.join(download_holds_dir, novo_nome)
                        contador += 1
                    shutil.move(str(arquivo_baixado_holds), caminho_final_holds)
                    print(f"✅ Arquivo Excel de holds salvo em: {caminho_final_holds}")
                else:
                    print("⚠️  Arquivo Excel de holds não foi baixado no tempo esperado.")
            else:
                print("⚠️  Não foi possível encontrar o botão de export Excel na página de Holds.")
        
        except Exception as e:
            print(f"⚠️  Erro ao baixar holds: {e}")
            import traceback
            traceback.print_exc()
            print("Continuando para Sales...")
        
        # ========== BAIXAR SALES ==========
        print("\n" + "="*60)
        print("INICIANDO DOWNLOAD DE SALES")
        print("="*60)
        
        try:
            # Passo 1: Clicar em "Sales"
            print("\n1. Clicando em 'Sales'...")
            try:
                link_sales = wait.until(
                    EC.element_to_be_clickable((By.XPATH, "//a[@href='/vSalesHome.aspx']"))
                )
                driver.execute_script("arguments[0].scrollIntoView(true);", link_sales)
                time.sleep(0.5)
                actions.move_to_element(link_sales).pause(0.3).click().perform()
                print("✅ Clicou em 'Sales'")
                time.sleep(2)
            except Exception as e:
                print(f"⚠️  Erro ao clicar em 'Sales': {e}")
                # Tentar método alternativo
                try:
                    link_sales = driver.find_element(By.XPATH, "//a[contains(text(), 'Sales')]")
                    driver.execute_script("arguments[0].scrollIntoView(true);", link_sales)
                    time.sleep(0.5)
                    actions.move_to_element(link_sales).pause(0.3).click().perform()
                    print("✅ Clicou em 'Sales' (método alternativo)")
                    time.sleep(2)
                except:
                    raise Exception("Não foi possível encontrar o link 'Sales'")
            
            # Passo 2: Clicar em "All Sale Orders"
            print("\n2. Clicando em 'All Sale Orders'...")
            try:
                # Usar um seletor mais genérico e robusto (sem datas fixas)
                link_all_sale_orders = wait.until(
                    EC.element_to_be_clickable((By.XPATH, "//a[contains(@href, 'listSaleOrders.aspx') and contains(., 'All Sale Orders')]"))
                )
                driver.execute_script("arguments[0].scrollIntoView(true);", link_all_sale_orders)
                time.sleep(0.5)
                # Tenta clique via JS que é instantâneo e evita bloqueios de sobreposição
                driver.execute_script("arguments[0].click();", link_all_sale_orders)
                print("✅ Clicou em 'All Sale Orders' (via JS)")
                time.sleep(2)
            except Exception as e:
                print(f"⚠️  Erro ao clicar em 'All Sale Orders': {e}")
                # Fallback: tentar qualquer link que contenha o texto
                try:
                    link_fallback = driver.find_element(By.LINK_TEXT, "All Sale Orders")
                    driver.execute_script("arguments[0].click();", link_fallback)
                    print("✅ Clicou em 'All Sale Orders' (link text)")
                except:
                    raise Exception("Não foi possível encontrar 'All Sale Orders'")
            
            print("\n3. Clicando em 'All'...")
            try:
                link_all = wait.until(
                    EC.element_to_be_clickable((By.XPATH, "//a[@class='underline' and contains(@title, 'Show All')]"))
                )
                driver.execute_script("arguments[0].scrollIntoView(true);", link_all)
                time.sleep(0.5)
                actions.move_to_element(link_all).pause(0.3).click().perform()
                print("✅ Clicou em 'All'")
                print("Aguardando página carregar após clicar em 'All'...")
                time.sleep(5)
            except Exception as e:
                print(f"⚠️  Erro ao clicar em 'All': {e}")
                try:
                    link_all = driver.find_element(By.XPATH, "//a[contains(@href, 'listSaleOrders') and contains(text(), 'All')]")
                    driver.execute_script("arguments[0].scrollIntoView(true);", link_all)
                    time.sleep(0.5)
                    actions.move_to_element(link_all).pause(0.3).click().perform()
                    print("✅ Clicou em 'All' (método alternativo)")
                    print("Aguardando página carregar após clicar em 'All'...")
                    time.sleep(5)
                except:
                    raise Exception("Não foi possível encontrar o link 'All'")
            
            print("\n4. Clicando na imagem do Excel para baixar...")
            download_sales_dir = os.path.abspath(os.path.join(os.getcwd(), "downloads", "sales"))
            
            # Aguardar um pouco mais para garantir que a página carregou
            print("Aguardando elementos da página carregarem...")
            time.sleep(2)
            
            img_excel_selectors = [
                "img[src*='icon_excel.gif']",
                "img[src*='excel']",
                "img[src='image/icon_excel.gif']",
                "img[src='/image/icon_excel.gif']",
                "img[alt*='Excel']",
                "img[alt*='excel']",
                "img[title*='Excel']",
                "img[title*='excel']",
            ]
            
            img_excel_encontrada = False
            
            # Primeiro, tentar encontrar e clicar na imagem diretamente
            for selector in img_excel_selectors:
                try:
                    print(f"Tentando encontrar imagem com seletor: {selector}")
                    img_excel = driver.find_elements(By.CSS_SELECTOR, selector)
                    if img_excel:
                        print(f"✅ Imagem do Excel encontrada! ({selector}) - Total: {len(img_excel)}")
                        for img in img_excel:
                            try:
                                # Verificar se está visível
                                if not img.is_displayed():
                                    print(f"  Imagem não está visível, pulando...")
                                    continue
                                
                                # Aguardar que esteja clicável
                                wait.until(EC.element_to_be_clickable(img))
                                
                                # Scroll até o elemento
                                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", img)
                                time.sleep(1)
                                
                                # Tentar múltiplos métodos de clique
                                print(f"  Tentando clicar na imagem (src: {img.get_attribute('src')})...")
                                
                                # Método 1: ActionChains
                                try:
                                    actions.move_to_element(img).pause(0.5).click().perform()
                                    print("  ✅ Clicou via ActionChains!")
                                    img_excel_encontrada = True
                                    break
                                except Exception as e1:
                                    print(f"  ⚠️  ActionChains falhou: {e1}")
                                
                                # Método 2: JavaScript click
                                if not img_excel_encontrada:
                                    try:
                                        driver.execute_script("arguments[0].click();", img)
                                        print("  ✅ Clicou via JavaScript!")
                                        img_excel_encontrada = True
                                        break
                                    except Exception as e2:
                                        print(f"  ⚠️  JavaScript click falhou: {e2}")
                                
                                # Método 3: Click direto
                                if not img_excel_encontrada:
                                    try:
                                        img.click()
                                        print("  ✅ Clicou diretamente!")
                                        img_excel_encontrada = True
                                        break
                                    except Exception as e3:
                                        print(f"  ⚠️  Click direto falhou: {e3}")
                                
                            except Exception as e:
                                print(f"  ⚠️  Erro ao processar imagem: {e}")
                                continue
                        
                        if img_excel_encontrada:
                            break
                except Exception as e:
                    print(f"  ⚠️  Erro com seletor {selector}: {e}")
                    continue
            
            # Se não encontrou a imagem, tentar procurar por link ou botão que contenha a imagem
            if not img_excel_encontrada:
                print("⚠️  Imagem do Excel não encontrada. Procurando por link/botão que contenha imagem do Excel...")
                try:
                    # Procurar por links que contenham imagem do Excel
                    links_com_excel = driver.find_elements(By.XPATH, "//a[.//img[contains(@src, 'excel') or contains(@src, 'Excel')]]")
                    if links_com_excel:
                        print(f"✅ Encontrado {len(links_com_excel)} link(s) com imagem do Excel")
                        for link in links_com_excel:
                            try:
                                if link.is_displayed():
                                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", link)
                                    time.sleep(1)
                                    # Tentar clicar no link
                                    try:
                                        actions.move_to_element(link).pause(0.5).click().perform()
                                        print("✅ Clicou no link que contém imagem do Excel!")
                                        img_excel_encontrada = True
                                        break
                                    except:
                                        driver.execute_script("arguments[0].click();", link)
                                        print("✅ Clicou no link via JavaScript!")
                                        img_excel_encontrada = True
                                        break
                            except:
                                continue
                except Exception as e:
                    print(f"⚠️  Erro ao procurar links: {e}")
            
            # Se ainda não encontrou, procurar por qualquer imagem com 'excel' no src
            if not img_excel_encontrada:
                print("⚠️  Tentando busca ampla por qualquer imagem com 'excel'...")
                try:
                    all_imgs = driver.find_elements(By.TAG_NAME, "img")
                    print(f"Total de imagens na página: {len(all_imgs)}")
                    for img in all_imgs:
                        try:
                            src = img.get_attribute("src") or ""
                            alt = img.get_attribute("alt") or ""
                            title = img.get_attribute("title") or ""
                            
                            if "excel" in src.lower() or "excel" in alt.lower() or "excel" in title.lower():
                                print(f"✅ Imagem do Excel encontrada por busca ampla!")
                                print(f"   src: {src}")
                                print(f"   alt: {alt}")
                                print(f"   title: {title}")
                                
                                if img.is_displayed():
                                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", img)
                                    time.sleep(1)
                                    
                                    # Tentar múltiplos métodos
                                    try:
                                        actions.move_to_element(img).pause(0.5).click().perform()
                                        print("✅ Clicou via ActionChains!")
                                        img_excel_encontrada = True
                                        break
                                    except:
                                        try:
                                            driver.execute_script("arguments[0].click();", img)
                                            print("✅ Clicou via JavaScript!")
                                            img_excel_encontrada = True
                                            break
                                        except:
                                            img.click()
                                            print("✅ Clicou diretamente!")
                                            img_excel_encontrada = True
                                            break
                        except Exception as e:
                            continue
                except Exception as e:
                    print(f"⚠️  Erro ao procurar imagem do Excel: {e}")
            
            # Se ainda não encontrou, tentar procurar por elementos com texto "Excel" ou "Export"
            if not img_excel_encontrada:
                print("⚠️  Tentando procurar por elementos com texto 'Excel' ou 'Export'...")
                try:
                    elementos_excel = driver.find_elements(By.XPATH, "//*[contains(text(), 'Excel') or contains(text(), 'Export')]")
                    for elemento in elementos_excel:
                        try:
                            if elemento.is_displayed() and elemento.is_enabled():
                                print(f"✅ Elemento encontrado: {elemento.tag_name} - {elemento.text[:50]}")
                                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", elemento)
                                time.sleep(1)
                                try:
                                    actions.move_to_element(elemento).pause(0.5).click().perform()
                                    print("✅ Clicou no elemento!")
                                    img_excel_encontrada = True
                                    break
                                except:
                                    driver.execute_script("arguments[0].click();", elemento)
                                    print("✅ Clicou no elemento via JavaScript!")
                                    img_excel_encontrada = True
                                    break
                        except:
                            continue
                except Exception as e:
                    print(f"⚠️  Erro ao procurar elementos: {e}")
            
            if img_excel_encontrada:
                # Aguardar o download do arquivo Excel
                print("Aguardando download do arquivo Excel de sales...")
                print(f"Procurando arquivo em: {download_sales_dir}")
                
                # Também verificar diretórios padrão do Chrome no Linux
                possiveis_diretorios_sales = [
                    download_sales_dir,
                    os.path.abspath(os.path.join(os.getcwd(), "downloads")),
                    os.path.expanduser("~/Downloads"),
                    os.path.expanduser("~/downloads"),
                    "/tmp",
                ]
                
                # Aguardar até que o arquivo seja baixado (máximo 60 segundos)
                max_wait_download = 60
                start_download = time.time()
                arquivo_baixado_sales = None
                arquivos_antes = {}  # Armazenar arquivos existentes antes do download
                
                # Registrar arquivos existentes antes do download
                for dir_path in possiveis_diretorios_sales:
                    if os.path.exists(dir_path):
                        try:
                            arquivos_antes[dir_path] = set(Path(dir_path).glob("*.xls*"))
                        except:
                            arquivos_antes[dir_path] = set()
                
                while time.time() - start_download < max_wait_download:
                    # Procurar em todos os diretórios possíveis
                    for dir_path in possiveis_diretorios_sales:
                        if not os.path.exists(dir_path):
                            continue
                        
                        # Listar arquivos Excel no diretório (.xls, .xlsx)
                        try:
                            arquivos_atuais = set(Path(dir_path).glob("*.xls*"))
                            # Verificar se há arquivos novos (que não existiam antes)
                            arquivos_novos = arquivos_atuais - arquivos_antes.get(dir_path, set())
                            
                            if arquivos_novos:
                                # Pegar o arquivo mais recente entre os novos
                                arquivo_mais_recente = max(arquivos_novos, key=os.path.getctime)
                                # Verificar se foi modificado recentemente (últimos 60 segundos)
                                tempo_modificacao = time.time() - os.path.getmtime(arquivo_mais_recente)
                                if tempo_modificacao < 60:
                                    arquivo_baixado_sales = arquivo_mais_recente
                                    print(f"Arquivo Excel encontrado em: {dir_path}")
                                    print(f"Nome do arquivo: {arquivo_baixado_sales.name}")
                                    break
                            
                            # Também verificar arquivos existentes que foram modificados recentemente
                            if not arquivo_baixado_sales:
                                arquivos = list(arquivos_atuais)
                                if arquivos:
                                    arquivo_mais_recente = max(arquivos, key=os.path.getmtime)
                                    tempo_modificacao = time.time() - os.path.getmtime(arquivo_mais_recente)
                                    if tempo_modificacao < 60:
                                        arquivo_baixado_sales = arquivo_mais_recente
                                        print(f"Arquivo Excel encontrado (modificado recentemente) em: {dir_path}")
                                        print(f"Nome do arquivo: {arquivo_baixado_sales.name}")
                                        break
                        except Exception as e:
                            continue
                    
                    if arquivo_baixado_sales:
                        break
                    
                    # Verificar também por arquivos .crdownload (download em andamento)
                    for dir_path in possiveis_diretorios_sales:
                        if not os.path.exists(dir_path):
                            continue
                        try:
                            arquivos_em_download = list(Path(dir_path).glob("*.crdownload"))
                            if arquivos_em_download:
                                print(f"Download em andamento em: {dir_path}")
                                break
                        except:
                            continue
                    
                    time.sleep(1)
                
                if arquivo_baixado_sales:
                    # Se o arquivo não está no diretório de sales, mover para lá
                    if str(arquivo_baixado_sales.parent) != download_sales_dir:
                        print(f"Movendo arquivo de {arquivo_baixado_sales.parent} para {download_sales_dir}...")
                    
                    # Renomear o arquivo com timestamp para evitar sobrescrita
                    timestamp = time.strftime("%Y%m%d_%H%M%S")
                    extensao = arquivo_baixado_sales.suffix
                    novo_nome = f"sales_{timestamp}{extensao}"
                    caminho_final = os.path.join(download_sales_dir, novo_nome)
                    
                    # Se o arquivo já existe com esse nome, adicionar número
                    contador = 1
                    while os.path.exists(caminho_final):
                        novo_nome = f"sales_{timestamp}_{contador}{extensao}"
                        caminho_final = os.path.join(download_sales_dir, novo_nome)
                        contador += 1
                    
                    # Mover o arquivo para o diretório de sales com o novo nome
                    shutil.move(str(arquivo_baixado_sales), caminho_final)
                    print(f"✅ Arquivo Excel de sales salvo em: {caminho_final}")
                    print(f"   Tamanho: {os.path.getsize(caminho_final)} bytes")
                else:
                    print("⚠️  Arquivo Excel não foi baixado no tempo esperado.")
                    print(f"   Verifique manualmente os diretórios: {', '.join(possiveis_diretorios_sales)}")
            else:
                print("⚠️  Não foi possível encontrar a imagem do Excel para clicar.")
        
        except Exception as e:
            print(f"⚠️  Erro ao baixar sales: {e}")
            import traceback
            print("\nDetalhes do erro:")
            traceback.print_exc()
            print("Continuando mesmo assim...")
        
        # Manter o navegador aberto por alguns segundos para visualização
        print("\nAguardando 5 segundos antes de fechar...")
        time.sleep(5)
        
    except Exception as e:
        print(f"Erro ao acessar a página: {e}")
        import traceback
        print("\nDetalhes do erro:")
        traceback.print_exc()
    
    finally:
        # Fechar o navegador
        driver.quit()
        print("Navegador fechado.")

if __name__ == "__main__":
    url = "https://aracruz.stoneprofits.com/listCustomers.aspx"
    try:
        # 1. Acessa a página e faz os downloads
        acessar_pagina(url)
        
        # 2. Após terminar o download, processa sequencialmente: clientes primeiro, depois sales
        print("\n" + "="*40)
        print("🤖 Iniciando processamento automático dos dados...")
        from processar_clientes import processar_e_salvar_clientes, comparar_ultimas_planilhas, enviar_para_n8n
        from processar_sales import processar_sales, enviar_sales_para_n8n
        from processar_holds import processar_holds, enviar_holds_para_webhook
        
        # PASSO 1: Processar e enviar CLIENTES primeiro
        print("\n" + "="*60)
        print("📋 PASSO 1: Processando CLIENTES...")
        print("="*60)
        caminho_final_clientes = processar_e_salvar_clientes()
        
        sucesso_clientes = False
        caminho_diff_clientes = None
        if caminho_final_clientes:
            caminho_diff_clientes = comparar_ultimas_planilhas()
            if caminho_diff_clientes:
                print("\n⏳ Enviando clientes para n8n (pode demorar alguns minutos na primeira vez)...")
                sucesso_clientes = enviar_para_n8n(caminho_diff_clientes)
            else:
                print("ℹ️  Nenhuma diferença de clientes detectada (primeira execução ou sem mudanças)")
                sucesso_clientes = True
        
        # PASSO 2: Processar e enviar HOLDS
        print("\n" + "="*60)
        print("📦 PASSO 2: Processando HOLDS...")
        print("="*60)
        caminho_diff_holds = processar_holds()
        if caminho_diff_holds:
            print("\n⏳ Enviando holds para webhook...")
            enviar_holds_para_webhook(caminho_diff_holds)
        else:
            print("ℹ️  Nenhuma diferença de holds detectada (primeira execução ou sem mudanças)")
        
        # PASSO 3: Processar SALES
        print("\n" + "="*60)
        print("📊 PASSO 3: Processando SALES...")
        print("="*60)
        caminho_diff_sales = processar_sales()
        
        # PASSO 4: Aguardar sucesso dos clientes antes de enviar sales
        if sucesso_clientes and caminho_diff_sales:
            print("\n" + "="*60)
            print("📤 PASSO 4: Enviando SALES para n8n (após sucesso dos clientes)...")
            print("="*60)
            enviar_sales_para_n8n(caminho_diff_sales)
            print(f"\n🏁 Fluxo completo finalizado com sucesso!")
        elif not sucesso_clientes:
            print(f"\n⚠️  Clientes não foram processados com sucesso. Sales não serão enviados.")
            print(f"   Verifique os logs acima para identificar o problema.")
        elif not caminho_diff_sales:
            print(f"\nℹ️  Sales processadas, mas nenhuma diferença detectada (primeira execução ou sem mudanças).")
            print(f"🏁 Fluxo completo finalizado!")
        
        print("="*40)
        
    except Exception as e:
        print(f"❌ Falha no fluxo diário: {e}")

