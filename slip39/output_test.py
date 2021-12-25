#import json
import qrcode

from fpdf		import FPDF, FlexTemplate

from .layout		import Region, Text, Image, Box, Coordinate


def test_Region():
    card_size			= Coordinate( y=2+1/4, x=3+3/8 )
    card_margin    		= 1/8
    card			= Box( 'card', 0, 0, card_size.x, card_size.y )
    #print( card )
    card_interior		= card.add_region_relative(
        Region( 'card-interior', x1=+card_margin, y1=+card_margin, x2=-card_margin, y2=-card_margin )
    )
    #print( card_interior )
    assert card_interior.x1 == card_margin
    assert card_interior.x2 == card_size.x - card_margin
    assert card_interior.y2 == card_size.y - card_margin
    assert card_interior.x2 - card_interior.x1 == card_size.x - card_margin * 2

    card_qr			= card_interior.add_region_proportional(
        Image( 'card-qr', x1=3/4, y1=1/2, x2=1, y2=1 )
    )
    card_qr.x1			= card_qr.x2 - 1.0
    card_qr.y1			= card_qr.y2 - 1.0
    #print( card_qr )
    assert card_qr.x1 == 2.25
    assert card_qr.y1 == 1.125

    elements			= list( card.elements() )[1:]
    #print( json.dumps( elements, indent=4 ))
    assert len( elements ) == 1
    assert elements[0]['type'] == 'I'

    card_top			= card_interior.add_region_proportional(
        Region( 'card-top', x1=0, y1=0, x2=1, y2=1/3 )
    )
    card_top.add_region_proportional(
        Text( 'card-title', x1=0, y1=0, x2=1, y2=40/100 )
    )

    elements			= list( card.elements() )[1:]
    #print( json.dumps( elements, indent=4 ))
    assert elements[1]['type'] == 'T'
    assert elements[1]['font'] == 'helvetica'
    assert elements[1]['size'] == 13

    pdf				= FPDF()
    pdf.add_page()

    tpl				= FlexTemplate( pdf, list( card.elements() ) )
    tpl['card-qr']		= qrcode.make( 'abc' ).get_image()
    tpl['card-title']		= 'Abc'
    tpl.render()

    tpl['card-qr']		= qrcode.make( 'abc' ).get_image()
    tpl['card-title']		= 'Xyz'
    tpl.render( offsetx = card_size.x * 25.4, offsety = card_size.y * 25.4 )

    #pdf.output( "test.pdf" ) # To view results in test.pdf, uncomment
