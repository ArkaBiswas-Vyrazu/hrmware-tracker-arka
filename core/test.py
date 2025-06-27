from bs4 import BeautifulSoup
import requests
import json
 
url = "https://www.gogomotor.com/en/used-cars/surveyed-searchkey-porsche%20panamera"
response = requests.get(url)
soup = BeautifulSoup(response.content, "html.parser")

with open("scrape.html", "w") as file:
    file.write(soup.prettify())

# Get the listing section
# main_div = soup.find("sectionc",class_="grid mx-auto w-full grid-cols-[repeat(1,minmax(270px,90%))] sm:grid-cols-[repeat(2,minmax(270px,330px))] md:grid-cols-[repeat(2,minmax(270px,330px))] lg:grid-cols-[repeat(2,minmax(270px,330px))] xl:grid-cols-[repeat(3,minmax(270px,330px))] gap-x-[24px] gap-y-[32px] justify-center")

# main_div = soup.find(id="__NEXT_DATA__").text

# with open("scrape.json", "w") as file:
#     file.write(json.dumps(json.loads(main_div), indent=4))
